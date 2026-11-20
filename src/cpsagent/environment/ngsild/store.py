"""`EntityStore` on an NGSI-LD Context Broker (Orion-LD), over its REST API.

  building, zones, devices  GET /ngsi-ld/v1/entities?type=Building|Zone|Device
  device                    GET /ngsi-ld/v1/entities/urn:ngsi-ld:Device:<id>
  write_state               PATCH /ngsi-ld/v1/entities/urn:ngsi-ld:Device:<id>/attrs (`state`)
  publish                   PATCH the `rssi` of the subject's PositioningSignal entity for
                            that beacon (created at its first reading)
  subscribe                 one NGSI-LD subscription on PositioningSignal; the broker
                            POSTs each notification to a receiver on the host
                            (`receiver.py`)

The @context. The project's terms (`data/ngsi-ld/context.jsonld`) are hosted by the broker
itself (NGSI-LD @context management, `/ngsi-ld/v1/jsonldContexts`, registered by the
seeding command), and every request names it in a `Link` header. The broker never has to
download it, and it survives a restart of the broker (Orion-LD keeps it in MongoDB).

Signals travel through the broker. `publish` updates the entity, then waits for the
broker's notification of that very reading and only then hands the notified signal to the
subscriber (the environment's control logic), on the caller's thread. A run on Orion-LD
therefore keeps the order of a run in memory: one reading is fully handled before the next
is published. A notification of a reading published by someone else, arriving meanwhile,
is handed over too, in arrival order. Orion-LD does not notify an update that changes
nothing; each reading of the mobility simulator has its own `observedAt`, so none is lost.

Order. An NGSI-LD listing has no defined order (Orion-LD lists by id). The store lists
zones and devices in the order of the scenario file it is given, as the in-memory store
does, because the interpreter's catalogue keeps that order; entities the scenario does not
name come after, by id.

The store only stores: the control logic computes a device's new state and writes it.
"""

import time
import uuid
from collections.abc import Callable
from queue import Empty
from typing import Any

import httpx

from ..model import Building, Device, PositioningSignal, Scenario, Zone
from ..store import SignalSink
from .entities import (
    CONTEXT_FILE,
    building_from,
    device_from,
    load_context,
    rssi_attribute,
    signal_entity,
    signal_from,
    signal_id,
    urn,
    zone_from,
)
from .receiver import NotificationReceiver

DEFAULT_URL = "http://localhost:1026"
API = "/ngsi-ld/v1"
LIMIT = 1000  # entities per listing (Orion-LD's maximum); the building has a few dozen
SUBSCRIPTION_NAME = "cps-agent positioning"
# Signal updates go on a connection of their own, closed after the answer: when the update
# came on a kept-alive connection, Orion-LD 1.13.0 now and then did not send its
# notification (15 of 60 runs lost one). With this and `-subCacheFlushIval 0`
# (docker-compose.yml) no notification was lost in 100 runs, 15,400 readings (docs/NGSI_LD.md).
CLOSE = {"Connection": "close"}


class BrokerError(Exception):
    """The broker answered with an error, or a notification did not come."""


class BrokerUnreachable(BrokerError):
    """No broker answers at the given URL."""


def link_header(context_url: str) -> dict[str, str]:
    return {
        "Link": f'<{context_url}>; rel="http://www.w3.org/ns/json-ld#context"; '
        'type="application/ld+json"'
    }


def check_reachable(http: httpx.Client, url: str) -> dict[str, Any]:
    """The broker's /version, or BrokerUnreachable with what to do."""
    try:
        response = http.get(f"{url}/version")
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BrokerUnreachable(
            f"no NGSI-LD broker reachable at {url} ({type(exc).__name__}); "
            "start it with `docker compose up -d`"
        ) from exc


def hosted_context(http: httpx.Client, url: str, context: dict[str, Any]) -> str | None:
    """URL under which the broker hosts `context`, if it does (found by content: the URL
    contains the broker's host name and an id the broker chose)."""
    listing = http.get(f"{url}{API}/jsonldContexts", params={"details": "true"})
    listing.raise_for_status()
    for entry in listing.json():
        if entry.get("kind") != "Hosted":
            continue
        hosted = http.get(f"{url}{API}/jsonldContexts/{entry['localId']}")
        if hosted.status_code == 200 and hosted.json() == context:
            return entry["URL"]
    return None


class NgsiLdStore:
    def __init__(
        self,
        url: str = DEFAULT_URL,
        *,
        scenario: Scenario | None = None,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        notify_host: str = "host.docker.internal",
        timeout_s: float = 5.0,
        context_file=CONTEXT_FILE,
    ) -> None:
        """`url`: the broker. `listen_host`/`listen_port`: where the notification receiver
        listens; `notify_host`: the name under which the broker's container reaches it.
        `scenario`: gives the order of the listings (none: by id)."""
        self.url = url.rstrip("/")
        self.endpoint = self.url
        self._timeout = timeout_s
        self._rank = {}
        if scenario is not None:
            names = [urn("Zone", z.zone_id) for z in scenario.zones]
            names += [urn("Device", d.device_id) for d in scenario.devices]
            self._rank = {entity_id: i for i, entity_id in enumerate(names)}
        self._listen = (listen_host, listen_port)
        self._notify_host = notify_host
        self._http = httpx.Client(timeout=timeout_s)
        self.version = check_reachable(self._http, self.url)
        context_url = hosted_context(self._http, self.url, load_context(context_file))
        if context_url is None:
            self._http.close()
            raise BrokerError(
                f"the broker at {self.url} does not host the project's @context: "
                "seed it with `python -m cpsagent.environment.ngsild.seed`"
            )
        self.context_url = context_url
        self._headers = link_header(context_url)
        buildings = self._list("Building")
        if not buildings:
            self._http.close()
            raise BrokerError(f"no Building at {self.url}: seed it first")
        self._building_names = {b["id"]: b["name"]["value"] for b in buildings}
        self._sinks: list[SignalSink] = []
        self._receiver: NotificationReceiver | None = None
        self._subscription: str | None = None
        self._created: set[str] = set()  # signal entities this store has created
        # Optional probe for the measurement harness: called once per published reading
        # with (signal, sent, answered, notified), perf_counter_ns instants of the update
        # request, of the broker's answer and of the notification's arrival.
        self.on_publish: Callable[[PositioningSignal, int, int, int], None] | None = None

    # --- REST helpers -------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {**self._headers, **kwargs.pop("headers", {})}
        try:
            return self._http.request(method, f"{self.url}{API}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise BrokerUnreachable(f"{method} {path}: {type(exc).__name__}") from exc

    @staticmethod
    def _check(response: httpx.Response, *ok: int) -> httpx.Response:
        if response.status_code not in ok:
            raise BrokerError(
                f"{response.request.method} {response.request.url.path}: "
                f"{response.status_code} {response.text[:200]}"
            )
        return response

    def _list(self, entity_type: str) -> list[dict[str, Any]]:
        params = {"type": entity_type, "limit": LIMIT}
        listed = self._check(self._request("GET", "/entities", params=params), 200).json()
        last = len(self._rank)
        return sorted(listed, key=lambda e: (self._rank.get(e["id"], last), e["id"]))

    # --- EntityStore: entities ----------------------------------------------------------

    def building(self) -> Building:
        return building_from(self._list("Building")[0])

    def zones(self) -> list[Zone]:
        return [zone_from(e, self._building_names) for e in self._list("Zone")]

    def devices(self) -> list[Device]:
        return [device_from(e) for e in self._list("Device")]

    def device(self, device_id: str) -> Device | None:
        response = self._request("GET", f"/entities/{urn('Device', device_id)}")
        if response.status_code == 404:
            return None
        return device_from(self._check(response, 200).json())

    def write_state(self, device_id: str, state: dict[str, Any]) -> None:
        body = {"state": {"type": "Property", "value": dict(state)}}
        path = f"/entities/{urn('Device', device_id)}/attrs"
        self._check(self._request("PATCH", path, json=body), 204)

    # --- EntityStore: positioning signals -----------------------------------------------

    def subscribe(self, sink: SignalSink) -> None:
        self._sinks.append(sink)
        if self._subscription is None:
            self._receiver = NotificationReceiver(*self._listen)
            endpoint = f"http://{self._notify_host}:{self._receiver.port}/notify"
            body = {
                "type": "Subscription",
                "subscriptionName": SUBSCRIPTION_NAME,
                "description": f"{SUBSCRIPTION_NAME} {uuid.uuid4()}",
                "entities": [{"type": "PositioningSignal"}],
                "notification": {"endpoint": {"uri": endpoint, "accept": "application/json"}},
            }
            response = self._check(self._request("POST", "/subscriptions", json=body), 201)
            self._subscription = response.headers["Location"].rsplit("/", 1)[-1]

    def publish(self, signal: PositioningSignal) -> None:
        entity_id = signal_id(signal.ref_subject, signal.ref_zone)
        sent = time.perf_counter_ns()
        if entity_id in self._created:
            path = f"/entities/{entity_id}/attrs"
            body = {"rssi": rssi_attribute(signal)}
            self._check(self._request("PATCH", path, json=body, headers=CLOSE), 204)
        else:
            self._create_signal(entity_id, signal)
        answered = time.perf_counter_ns()
        if not self._sinks:
            return  # nobody subscribed: no notification to wait for
        notified = self._deliver_until(signal)
        if self.on_publish is not None:
            self.on_publish(signal, sent, answered, notified)

    def _create_signal(self, entity_id: str, signal: PositioningSignal) -> None:
        """First reading of this subject and beacon for this store. An entity left by an
        earlier run is replaced, so the first reading is a creation, which is notified
        even when it repeats that run's last reading."""
        entity = signal_entity(signal)
        response = self._request("POST", "/entities", json=entity, headers=CLOSE)
        if response.status_code == 409:
            self._check(self._request("DELETE", f"/entities/{entity_id}", headers=CLOSE), 204)
            response = self._request("POST", "/entities", json=entity, headers=CLOSE)
        self._check(response, 201)
        self._created.add(entity_id)

    def _deliver_until(self, signal: PositioningSignal) -> int:
        """Hand every notified signal to the subscribers until the notification of
        `signal` arrives; return its arrival instant."""
        assert self._receiver is not None
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                arrived, entity = self._receiver.entities.get(
                    timeout=max(0.0, deadline - time.monotonic())
                )
            except Empty:
                raise BrokerError(
                    f"no notification for {signal.ref_subject}/{signal.ref_zone} within "
                    f"{self._timeout:g} s: is the receiver reachable from the broker at "
                    f"{self._notify_host}?"
                ) from None
            if "rssi" not in entity:
                continue  # a deletion (`deletedAt`): the entity of an earlier run replaced
            notified = signal_from(entity)
            for sink in list(self._sinks):
                sink(notified)
            if _same_reading(notified, signal):
                return arrived

    def close(self) -> None:
        if self._subscription is not None:
            try:
                self._request("DELETE", f"/subscriptions/{self._subscription}")
            except BrokerError:
                pass  # the broker is gone: nothing left to clean up there
            self._subscription = None
        if self._receiver is not None:
            self._receiver.close()
            self._receiver = None
        self._sinks.clear()
        self._http.close()


def _same_reading(a: PositioningSignal, b: PositioningSignal) -> bool:
    """Same subject, beacon, RSSI and time; the broker keeps times to the millisecond."""
    return (a.ref_subject, a.ref_zone, a.rssi) == (b.ref_subject, b.ref_zone, b.rssi) and abs(
        (a.observed_at - b.observed_at).total_seconds()
    ) < 0.001


__all__ = ["BrokerError", "BrokerUnreachable", "NgsiLdStore"]
