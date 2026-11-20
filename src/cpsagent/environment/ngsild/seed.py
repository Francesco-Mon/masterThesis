"""Load the scenario into an NGSI-LD broker, idempotently.

Run: python -m cpsagent.environment.ngsild.seed [--url http://localhost:1026]
                                                [--scenario data/scenario.yaml]

After a run the broker holds exactly the scenario: the project's @context hosted by the
broker, one Building, its Zones and its Devices with every device in its `state` from the
scenario (its defaultState). Running it again gives the same content. It also removes what
runs leave behind: every PositioningSignal entity, the Zone and Device entities that are
not in the scenario, and the positioning subscriptions of NgsiLdStore (so do not seed
while an agent or the UI is running on the same broker).
"""

import argparse
from typing import Any

import httpx

from ..model import DEFAULT_SCENARIO, Scenario, load_scenario
from .entities import CONTEXT_FILE, load_context, scenario_entities
from .store import (
    API,
    DEFAULT_URL,
    LIMIT,
    SUBSCRIPTION_NAME,
    BrokerError,
    check_reachable,
    hosted_context,
    link_header,
)


def _ok(response: httpx.Response, *codes: int) -> httpx.Response:
    if response.status_code not in codes:
        raise BrokerError(f"{response.request.method} {response.request.url.path}: "
                          f"{response.status_code} {response.text[:300]}")  # fmt: skip
    return response


def ensure_context(http: httpx.Client, url: str, context: dict[str, Any]) -> str:
    """Have the broker host the @context (once) and return its URL."""
    found = hosted_context(http, url, context)
    if found is None:
        _ok(http.post(f"{url}{API}/jsonldContexts", json=context), 201)
        found = hosted_context(http, url, context)
    if found is None:
        raise BrokerError("the broker did not keep the @context it was given")
    return found


def seed(
    url: str = DEFAULT_URL, scenario: Scenario | None = None, context_file=CONTEXT_FILE
) -> dict[str, int]:
    """Make the broker hold the scenario; returns what was written and removed."""
    scenario = scenario or load_scenario()
    url = url.rstrip("/")
    with httpx.Client(timeout=10.0) as http:
        check_reachable(http, url)
        headers = link_header(ensure_context(http, url, load_context(context_file)))

        subscriptions = _ok(
            http.get(f"{url}{API}/subscriptions", params={"limit": LIMIT}, headers=headers), 200
        ).json()
        stale = [s["id"] for s in subscriptions if s.get("subscriptionName") == SUBSCRIPTION_NAME]
        for sub_id in stale:
            _ok(http.delete(f"{url}{API}/subscriptions/{sub_id}"), 204, 404)

        entities = scenario_entities(scenario)
        wanted = {e["id"] for e in entities}
        leftover = []
        for entity_type in ("PositioningSignal", "Device", "Zone", "Building"):
            listed = _ok(
                http.get(
                    f"{url}{API}/entities",
                    params={"type": entity_type, "limit": LIMIT},
                    headers=headers,
                ),
                200,
            ).json()
            leftover += [e["id"] for e in listed if e["id"] not in wanted]
        if leftover:
            _ok(http.post(f"{url}{API}/entityOperations/delete", json=leftover), 200, 204)

        # Upsert replaces an existing entity whole: states go back to the scenario's.
        _ok(
            http.post(
                f"{url}{API}/entityOperations/upsert",
                json=entities,
                headers={**headers, "Content-Type": "application/json"},
            ),
            200,
            201,
            204,
        )
    return {"entities": len(entities), "removed": len(leftover), "subscriptions": len(stale)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--scenario", default=str(DEFAULT_SCENARIO))
    args = parser.parse_args()
    done = seed(args.url, load_scenario(args.scenario))
    print(
        f"Seeded {args.url}: {done['entities']} entities (building, zones, devices) written, "
        f"{done['removed']} leftover entities and {done['subscriptions']} old positioning "
        "subscriptions removed."
    )


if __name__ == "__main__":
    main()
