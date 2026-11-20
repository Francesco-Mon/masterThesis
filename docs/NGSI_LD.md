# The environment on Orion-LD

The environment (the manager's side: scope, following the person with triggers,
interpretation service, environmental policy, command semantics) runs on one of two entity
stores, with the same control logic:

- **in memory** (`InMemoryStore`): the entities are Python objects of the agent's process,
  and a positioning signal is handed to the environment by a direct call;
- **Orion-LD** (`NgsiLdStore`): the entities live in an NGSI-LD Context Broker (Orion-LD
  1.13.0 with MongoDB 4.4.29, in Docker) and are reached over its REST API; a positioning
  signal is an update of a `PositioningSignal` entity and comes back to the environment as
  an NGSI-LD notification.

`EnvironmentControl` (`src/cpsagent/environment/control.py`) holds the control logic and
talks to the entities only through the `EntityStore` protocol (`store.py`): read the
building, the zones and the devices, read one device, write a device's state, publish a
positioning signal, subscribe to positioning signals. It does not know which store it
uses (tested: it imports no concrete store). `EmulatedEnvironment` is that control logic
over the in-memory store, and `ngsild_environment(url)` the same logic over Orion-LD.

So two runs of the same scenario differ only in where the entities live and how signals
travel. Everything else (records, commands, restorations, device states, zone changes,
GroundingRequests) is tested to be identical (`tests/ngsild/`, see "Functional
equivalence" below). Timings differ, and the harness measures them on both stores.

## Differences between the two representations

| Aspect | In memory (emulator) | NGSI-LD (Orion-LD) |
|---|---|---|
| Entity ids | Plain ids from `data/scenario.yaml` (`lamp_hallway`, `hallway`); the building has a name only | URNs: `urn:ngsi-ld:Device:lamp_hallway`, `urn:ngsi-ld:Zone:hallway`, `urn:ngsi-ld:Building:lab_building` (made from the building's name), `urn:ngsi-ld:Person:user-1` (target of `refSubject` only, no entity) |
| Positioning signal | A `PositioningSignal` object per reading, never stored | One entity per subject and beacon zone, `urn:ngsi-ld:PositioningSignal:user-1:hallway`, created at its first reading and then updated at each reading |
| Vocabulary | Pydantic field names, camelCase aliases | JSON-LD `@context` `data/ngsi-ld/context.jsonld`: every project term maps into `https://example.org/cps-agent/ns#` (a placeholder namespace, not resolvable); `name` and `location` come from the NGSI-LD core context (v1.9, added by the broker) |
| Attribute forms | Plain fields | Relationships: `refBuilding` (Zone), `refZone` (Device, PositioningSignal), `refSubject` (PositioningSignal). Properties: `name`, `category`, `managementPolicy`, `adjacency` (list of zone URNs), `controlledProperty`, `supportedCommand`, `state`, `defaultState`, `signalType`, `rssi`. GeoProperty: `location`. The time of a reading is the `observedAt` of its `rssi` Property |
| Values read back | Python values as written | JSON-LD compaction turns a one-element array into its element (`supportedCommand: ["setSetpoint"]`, `adjacency` of lobby) and the broker drops the `.0` of an integral number (setpoint `21.0`, RSSI `-55.0`); times are kept to the millisecond. The store restores lists and floats (`entities.py`) |
| Order of listings | Scenario order | NGSI-LD gives a listing no order (Orion-LD lists by id). The store sorts zones and devices by the scenario file's order, because the interpreter's catalogue keeps that order (it is part of the GroundingRequest); other entities follow, by id |
| Access | In-process method calls on objects | REST over HTTP on `localhost:1026`: one GET per listing, one GET per device, one PATCH per state change (see the round trips below) |
| Device state update | Assignment of the new state | `PATCH /ngsi-ld/v1/entities/{id}/attrs` with the whole `state` Property |
| Command semantics | `commands.py`, called by the control logic | The same: the control logic (the device simulator side) computes the new state from the command; the broker only stores the result. Orion-LD knows nothing of commands |
| Positioning signals | Mobility simulator -> `publish` -> direct call to the environment | Mobility simulator -> `publish` -> PATCH of the signal entity's `rssi` (POST at its first reading) -> Orion-LD matches the store's subscription on `PositioningSignal` -> HTTP POST of the notification to a receiver on the host -> queue -> the store hands the notified signal to the environment, on the publishing thread |
| Notifications versus callbacks | Callbacks, synchronous, never lost | NGSI-LD notifications, asynchronous. `publish` waits for the notification of its own reading, so one reading is fully handled before the next is published, as in memory. Orion-LD does not notify an update that changes nothing (the simulator never sends one: each reading has a new `observedAt`). NGSI-LD promises no delivery: a reading whose notification does not come within 0.5 s is read back from the broker (see "Lost notifications") |
| Environment time | `observedAt` of the latest signal | The same, read from the notified signal |
| Scope and tokens | Control logic: tokens issued to the agents of `scenario.yaml`, scope checked on every call | The same control logic, in the agent's Python process. Orion-LD has no tokens and no scope here (no authorization layer in front of it) |
| Following the person (triggers) | Control logic, from the signals it receives | The same control logic, from the notified signals. The triggers are not NGSI-LD subscriptions: one subscription on every `PositioningSignal` feeds the control logic, which arms and fires its triggers itself |
| Environmental policy and restoration | Control logic; restored states written to the store | The same; each restoration is a PATCH of the device's `state` |
| Interpretation service | Control logic: catalogue and adjacency built from the store, grounder called in process | The same; the catalogue is built from two GETs (zones, devices) per request |
| Agent to environment | In-process calls (Environment Binding, Environment Interface) | The same: only the environment to entity store boundary is NGSI-LD. The measured latencies include the broker round trips, not a network hop between agent and environment |
| Configuration | Scenario file | Agents, scope and the scripted paths still come from the scenario file (the manager's configuration); the building, zones and devices are read from the broker, loaded there by the seeding command |
| Failures | None | `BrokerUnreachable` (no broker at the URL), `BrokerError` (an error answer, a broker not seeded, a reading neither notified nor held by the broker); a reading whose notification is lost is read back and counted (`recovered`) |

Round trips to the broker per operation, as counted by the harness (in memory the same
calls are method calls):

| Operation (as the agent sees it) | Store calls (Orion-LD requests) |
|---|---|
| `listZones` | 1 GET (zones) |
| `listDevices()` | 1 GET (devices) |
| `listDevices(zoneId, controlledProperty)` | 2 GETs (zones, to check the zone exists; devices) |
| `getDeviceState(deviceId)` | 1 GET (the device) |
| `invokeCommand(deviceId, command)` | 3: GET (the Interface reads the device), GET (the environment reads it again), PATCH (`state`) |
| interpretation request | 2 GETs (zones, devices) for the catalogue and adjacency |
| positioning signal | 1 PATCH (1 POST at the first reading of a beacon) and 1 notification; a trigger that fires adds 1 GET (zones) |
| restoration | 1 GET (the device) and 1 PATCH (`state`) |

A call refused by the agent's own Scope Guard (e.g. `listDevices(zoneId=server_room)`)
reaches neither store.

### Choices

- **Where the `@context` is served.** Orion-LD hosts it: the seeding command registers
  `context.jsonld` through the NGSI-LD @context management API
  (`POST /ngsi-ld/v1/jsonldContexts`), and the store finds it by content
  (`GET /ngsi-ld/v1/jsonldContexts?details=true`) and names it in the `Link` header of
  every request. The broker never downloads it, so nothing on the host has to serve it, and
  it survives a restart of the broker (Orion-LD keeps it in MongoDB). Its URL contains the
  broker's host name (`http://orion:1026/ngsi-ld/v1/jsonldContexts/<id>`; `hostname: orion`
  in `docker-compose.yml`), and the client uses it only as a name. Dropped: serving the file
  from the notification receiver (the broker would depend on a process of the agent's
  machine, and the URL would change with the receiver's port); an inline `@context` in
  each body (a GET needs a URL to compact the answer).
- **How the broker reaches the receiver.** The store starts a small HTTP server on the
  host (`receiver.py`, standard library), listening on `127.0.0.1` on a free port, and
  subscribes with the endpoint `http://host.docker.internal:<port>/notify`. Docker Desktop
  on macOS resolves `host.docker.internal` to the host and forwards the connection to the
  loopback address. On Linux, `docker-compose.yml` defines the name with
  `host-gateway`, and the receiver has to listen on an address of the Docker bridge
  (`NgsiLdStore(listen_host="0.0.0.0")`). Each store creates its subscription (named
  `cps-agent positioning`) when the environment subscribes and deletes it when closed; the
  seeding command deletes any left by a run that crashed.
- **Lost notifications.** On this machine (macOS, Docker Desktop 28.2.2) Orion-LD 1.13.0
  now and then accepts an update (204) and never sends its notification: the
  subscription's `timesSent` stays one below the number of updates, no failure is recorded,
  and no connection reaches the receiver. Two settings make it rarer. Each signal update
  goes on its own HTTP connection, closed after the answer: with kept-alive connections 15
  of 60 walks of the simulator alone lost a notification. The broker runs with
  `-subCacheFlushIval 0` (no periodic flush of the subscription counters): with the
  default 10 s, 1 of 40 such walks still lost one. With both, 100 walks of the simulator
  alone (15,400 readings) lost none, but full scenario runs (agent, reads and state writes
  interleaved) still lost one now and then: 2 of 40 runs in one series, 2 of 100 with every
  request on a new connection, 0 of 100 in the last series, and 2 runs of the Orion-LD test
  suite out of about 25. NGSI-LD promises no delivery, so the store does not depend on it:
  if the notification of a reading has not come within 0.5 s, it reads the signal entity
  back and, if the broker holds that reading, hands it to the environment itself; the
  reading counts in `NgsiLdStore.recovered`, a late notification of it is dropped, and the
  harness marks its row `"recovered": true` (its delivery time includes the 0.5 s wait, so
  it belongs in no latency statistic; the harness summary lists it apart). If the broker
  does not hold the reading either, the store raises `BrokerError`. A test drops a
  notification on purpose and checks that the run stays identical to the in-memory one.
  Reads and state updates keep the connection alive.
- **Seeding.** `python -m cpsagent.environment.ngsild.seed` makes the broker hold exactly
  the scenario: it registers the `@context` if needed, upserts (replaces) the building, the
  zones and the devices (every device back to its scenario state), and removes every
  `PositioningSignal` entity, any zone or device not in the scenario and the old positioning
  subscriptions. Running it twice gives the same content. The UI and the harness seed
  before each session or phase, so each starts from the scenario's state, as in memory.

## Running on Orion-LD

```bash
pip install -e ".[dev,ngsild]"                    # the HTTP client, pinned (httpx 0.28.1)
docker compose up -d                              # Orion-LD on http://localhost:1026
curl -s localhost:1026/version                    # "orionld version": "1.13.0"
python -m cpsagent.environment.ngsild.seed        # load data/scenario.yaml
```

| What | Command |
|---|---|
| Tests on Orion-LD (functional equivalence, harness, UI session) | `pytest -m ngsild` |
| UI on Orion-LD | `streamlit run src/cpsagent/ui/app.py`, sidebar "Entity store": Orion-LD, URL `http://localhost:1026` |
| Harness, in memory | `python -m cpsagent.bench.backends --store memory --repeats 30` |
| Harness, on Orion-LD | `python -m cpsagent.bench.backends --store ngsild --repeats 30` |
| Stop the broker and delete its data | `docker compose down -v` |

In code:

```python
from cpsagent.environment.ngsild import ngsild_environment
env = ngsild_environment("http://localhost:1026", interpreter)  # seeded broker
...
env.close()  # deletes the store's subscription, stops the receiver
```

The default `pytest` deselects the `ngsild` tests and needs no Docker. With
`pytest -m ngsild`, a broker that does not answer fails the tests with the command that
starts it. In the UI, choosing Orion-LD at a URL where no broker answers shows
"Orion-LD not available at ..." and no session starts.

Versions: Orion-LD `quay.io/fiware/orion-ld:1.13.0`, the release pinned by the Orion-LD
README (latest release, November 2026); MongoDB `mongo:4.4.29`, the 4.4 line of the
official Orion-LD compose examples (`docker/docker-compose.yml` and
`doc/manuals-ld/installation-guide-docker.md` in the FIWARE/context.Orion-LD repository,
which require MongoDB 4.2 or higher), pinned to its last patch release. The harness records
the versions the broker reports (`/ngsi-ld/ex/v1/version`).

## Functional equivalence

`tests/ngsild/test_equivalence.py`, with the keyword grounder and the broker seeded before
each test:

- the broker read back gives the scenario's building, zones and devices;
- `walk_in_the_light` and `doorway_linger`, seeds 0 and 3, each run with "I want to walk
  in the light": the transition records (states, guards, zone, intent, action, outcome),
  the replies, the commands, the zone changes, the environment's triggers, the
  restorations (device, zone, state, reason, time), the number of forwarded signals and
  the device states before and after closing equal the in-memory run and the baseline
  recorded before the split (`tests/regression/store_baseline.json`);
- the zone changes of `doorway_linger` (no request) equal the regression baseline;
- the GroundingRequest of each of the 210 dataset cases, built from the broker's entities,
  has the baseline's hash;
- the calls of the command-line demo (allowed, out of scope, unknown zone or device,
  unsupported command, invalid value, operation not allowed) give the same ToolResults and
  final states; a zone estimate outside the scope is refused before interpretation;
- a state written by a command is in the broker, and closing the subscription restores it
  there.

## Measurement harness

`python -m cpsagent.bench.backends --store memory|ngsild` runs the same phases on the
chosen store, with the keyword grounder only, and writes raw rows; it plots nothing. Each
repeat runs four phases on a fresh environment (on Orion-LD the broker is seeded first):
`operations` (each Interface operation and the interpretation request, `--calls` times),
`requests` (six requests to the engine), and one full run of each scripted path with "I
want to walk in the light". The first `--warmup` repeats (default 2) are written too, with
`"warmup": true`. The ticks of a path are played one after the other without waiting a
simulated second, so wall-clock delays measure processing; delays in ticks are reported
apart.

Output, `results/bench/<store>-<UTC time>/`:

- `metadata.json`: store, repeats, warm-ups, seed, calls, paths, interpreter, Python and
  httpx versions, machine (OS, CPU, model, memory), commit and whether the tree was dirty,
  clock, the number of recovered signals, and on Orion-LD the broker URL and the versions it reports (Orion-LD, MongoDB
  server, mongoc driver, core context);
- `events.jsonl`: one row per measured event, with `runId`, `store`, `repeat`, `warmup`,
  `phase`, `measure`; durations in nanoseconds of `time.perf_counter_ns`.

| `measure` | One row per | Fields |
|---|---|---|
| `operation` | Interface call or interpretation request | `operation`, `args`, `ok`, `latency_ns` (as the agent sees it), `storeCalls` and `store_ns` (time inside the store); for `interpret` also `interpreter_ns` and `overhead_ns` (latency minus interpreter) and `result` |
| `signal` | Positioning signal published | `tick`, `zone`, `firstReading`, `forwarded` (reached the agent), `publish_ns` (publish call), `delivery_ns` (publication to the agent's Localization); on Orion-LD `update_ns` (PATCH or POST answered), `notification_ns` (answer to notification arrival) and `recovered` (no notification: read back after 0.5 s) |
| `trigger` | Trigger of the environment | `tick`, `zone`, `ns` from the publication of the signal that fired it |
| `zone_change` | True zone change of the path | `tick`, `from`, `to`; `trigger`, `estimate`, `lampOn`: each `{ticks, ns}` from the start of the tick of the true change to the environment's trigger, to the agent's estimate, to the lamp of the new zone switched on |
| `cycle` | Engine cycle (a request, or a re-planning on a zone change) | `kind`, `label` (request text or zone), `total_ns` (text in to reply out for a request), `transitions` |
| `cycle_state` | State left in a cycle | `state` (Perceive, Interpret, Plan, Act, Observe, Recover; `reply` for what follows the last transition of a request), `guard`, `ns` |
| `scenario_run` | Full run of a path | `total_ns`, `walk_ns`, `close_ns`, `ticks`, `signals`, `forwarded`, `commands`, `restorations` |
| `restoration` | Restoration by the policy | `deviceId`, `zoneId`, `reason`, `tick`; for `person_left_zone` `afterEnvExitTicks` and `afterTrueExitTicks` (ticks since the environment's placement, or the true position, left the zone) and `ns` (within the tick that completed it); for `subscription_closed`, `ns` from the start of the closing |

At the end the harness prints the median and the 95th percentile of the main measures,
warm-ups excluded, as a check that it worked. The measures shown in the thesis, and their
analysis, are to be chosen on these raw rows.
