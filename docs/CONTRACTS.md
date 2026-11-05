# CONTRACTS - the four formats exchanged between components

Each contract = one Pydantic model in `src/cpsagent/contracts/`, one exported JSON Schema in `docs/schemas/`, and at least 3 valid + 3 invalid example messages used in tests. Field names follow the thesis (camelCase on the wire, snake_case allowed in Python with aliases). The shapes below are the original proposal; every change made in the code is recorded in DECISIONS.md.

## C1 - ZoneEstimate (R5 response, R6 event)

```json
{"zoneId": "hallway", "confidence": 0.87, "observedAt": "2026-11-10T09:30:12Z", "previousZoneId": "livingroom"}
```
- `zoneId`: must exist in the bound spatial model. `confidence`: float in [0,1]. `previousZoneId`: optional.
- Zone-change event (R6) = `{"type": "zone_changed", "estimate": <ZoneEstimate>}`.

## C2 - Grounding request and result (R7 / R8)

R7 request:
```json
{
  "text": "I want to walk in the light",
  "language": "en",
  "zone": {"zoneId": "hallway", "confidence": 0.87, "observedAt": "...", "previousZoneId": "livingroom"},
  "catalogue": [
    {"zoneId": "hallway", "devices": [{"deviceId": "lamp_hallway", "category": "lamp", "controlledProperty": "light", "supportedCommand": ["on", "off", "dim"]}]},
    {"zoneId": "corridor", "devices": [{"deviceId": "lamp_corridor", "category": "lamp", "controlledProperty": "light", "supportedCommand": ["on", "off"]}]}
  ],
  "adjacency": {"hallway": ["livingroom", "corridor"]},
  "history": []
}
```

R8 result - a discriminated union:
```json
{"kind": "intent", "intent": {"action": "activate", "controlledProperty": "light", "scope": "path", "persistence": "following", "confidence": 0.9}}
```
```json
{"kind": "intent", "intent": {"action": "activate", "controlledProperty": "light", "scope": "current_zone", "persistence": "one_off", "confidence": 0.95, "targetZoneId": "kitchen"}}
```
```json
{"kind": "intent", "intent": {"action": "set", "controlledProperty": "temperature", "scope": "current_zone", "persistence": "one_off", "confidence": 0.9, "value": 22}}
```
```json
{"kind": "clarification", "question": "Which room do you mean?", "reason": "ambiguous_target"}
```
```json
{"kind": "unsupported", "reason": "capability_absent"}
```
- `action`: closed enum (activate, deactivate, increase, decrease, set, query), taken from the capability catalogue vocabulary.
- `controlledProperty`: **a property present in the catalogue** (validated in code, not trusted from the LLM).
- `scope`: enum {current_zone, path, environment}. `persistence`: enum {one_off, following}. `confidence`: [0,1].
- `targetZoneId` (optional): present only when the user names a zone other than the current one ("turn on the kitchen light" said in the hallway). It replaces the current zone, so it is allowed only with `scope: current_zone`; it must be a catalogued zone (= in the agent's scope), otherwise the result is `unsupported` / `out_of_scope`. Checked in code (validation context `catalogue_zones`), like `controlledProperty`.
- `value` (optional number): present **exactly** when `action` is `set` ("set the thermostat to 22", "dim the lamp to 40%"); `set` without a number is invalid (the grounder asks for clarification instead). Unit = the property's: percent for `light` (brightness) and `shading` (0 = blinds open, 100 = closed: the value grows with the property, like `increase`; the planner sends `setPosition` with 100 - value, since a blind's position is % open), degrees Celsius for `temperature`. Ranges are checked by the environment (`invokeCommand` fails on an out-of-range value), not by the contract. The planner maps `set` to `dim` / `setPosition` / `setSetpoint` with this value; a device without that command gives no step (`command_absent`).
- Any candidate (A: LLM, C: embeddings, ...) implements `Grounder.ground(request) -> GroundingResult` and nothing else. Parsing errors never escape: after the bounded retry the result is `clarification`/`unsupported` with a `reason`.

## C3 - Tool call and result (R12)

```json
{"operation": "invokeCommand", "args": {"deviceId": "lamp_hallway", "command": "on", "value": null}}
```
```json
{"ok": true, "operation": "invokeCommand", "state": {"deviceId": "lamp_hallway", "power": "on"}, "error": null}
```
- `operation` is a closed enum of exactly: `listZones`, `listDevices`, `getDeviceState`, `invokeCommand`. Anything else is rejected by the Environment Interface with `ok:false, error:"operation_not_allowed"`.
- `invokeCommand` is rejected if `command` is not in the device's `supportedCommand` (`error:"command_not_supported"`) or the device is outside the negotiated scope.

## C4 - Event record (R16)

```json
{
  "seq": 3, "time": "2026-11-10T09:30:13Z", "session": "sess-001",
  "from": "Plan", "to": "Act", "guard": "T4",
  "zone": {"zoneId": "hallway", "confidence": 0.87, "observedAt": "...", "previousZoneId": null},
  "intent": {"action": "activate", "controlledProperty": "light", "scope": "path", "persistence": "following", "confidence": 0.9},
  "action": {"operation": "invokeCommand", "args": {"deviceId": "lamp_hallway", "command": "on"}},
  "outcome": null
}
```
Stored form (JSONL line): `{"record": <C4>, "salt": "<hex>", "commitment": "<hex>", "link": "<hex>"}`. See SPEC section 7 for the hash rules.

## Also fixed here

- **ActionPlan**: `{"steps": [{"deviceId", "command", "value", "guard": {"type": "now"} | {"type": "on_enter_zone", "zoneId": "..."}}], "validFor": <ZoneEstimate>}`.
- **Device state** (emulator): at least `power` for lamps; `position` for blinds; `setpoint` for thermostats.
- Time: always timezone-aware UTC; a clock is injected so tests are deterministic.
