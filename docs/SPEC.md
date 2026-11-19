# SPEC - what the thesis (Ch.4-5) fixes

Extract of the system specification. Names are normative: code and thesis use the same ones.

## 1. Components and relations

Components: User Interface (F1), Localization (F2), Intent Grounding (F3), Orchestration Engine (F4-F6), Environment Binding, Environment Interface, Event Log (F7), Shared Ledger (designed in the thesis, not implemented in the prototype), Intelligent Environment (emulated).

| ID | From -> To | Meaning | Implemented as |
|---|---|---|---|
| R1/R4 | User <-> UI | voice or text in / text or speech out | Streamlit chat, STT wrapper |
| R2 | UI -> Engine | request (text, user id, timestamp, language) | function call (in-process) |
| R3 | Engine -> UI | status, message, optional clarification question | return value / callback |
| R5 | Engine -> Localization | ZoneEstimate query | function call |
| R6 | Localization -> Engine | zone-change event carrying new ZoneEstimate | asyncio queue / callback |
| R7 | Engine -> Intent Grounding | request text, language, ZoneEstimate, short history; Intent Grounding is a service of the environment, reached through the bound session (section 3) | `EnvironmentBackend.interpret`, across the agent-environment boundary |
| R8 | Intent Grounding -> Engine | StructuredIntent or clarification-needed | return value, Pydantic-validated and checked by the environment against its catalogue |
| R9/R10 | Engine <-> Binding | binding request / session descriptor: scope, person's zone and followed neighbourhood | function call |
| R11 | Binding -> Env. Interface | configuration | object injection |
| R12 | Engine <-> Env. Interface | tool call and result (the 4 operations) | function call |
| R13 | Env. Interface -> Localization | raw positioning signal | callback |
| R14/R15 | Binding / Env. Interface <-> Environment | NGSI-LD in the thesis | `EnvironmentBackend` Protocol, implemented by the **emulator in-process** (same entity names) |
| R16 | Engine -> Event Log | event record, asynchronous, never blocks the loop | in-process queue |
| R17 | Event Log <-> Ledger | anchoring | **not implemented** (optional) |

Boundaries: (1) User <-> Agent, (2) Agent <-> Environment, (3) Agent <-> Ledger.

## 2. Environment model

| Entity | Key properties | Relationships |
|---|---|---|
| `Building` | `name`, `category`, `location`, `managementPolicy` | - |
| `Zone` | `name`, `zoneId`, `adjacency` | `refBuilding` |
| `Device` | `category`, `controlledProperty`, `supportedCommand`, `state`, `defaultState` | `refZone` |
| `PositioningSignal` | `signalType`, `rssi`, `observedAt` | `refZone`, `refSubject` |

- `supportedCommand` is what makes capability discovery possible: the catalogue is *queried*, never assumed. A request for a capability no device in the environment offers ends in a clarification / Recover, never in a hallucinated command.
- Control stays with the manager of the environment; the agent is a client. The environment fixes the scope of the agent's token, refuses any call outside it and decides what it lists.
- `adjacency` lists which zones are reachable from which; the planner uses it to reason about movement.
- `defaultState` (NGSI-LD property of `Device`, same shape as `state`) is fixed by the manager of the environment: lamps off, blinds closed, thermostats at 21 °C in the reference scenario. The building starts in it. The scenario loader accepts only a state that one command of the device's category gives from the initial state (a lamp "on" at 0% brightness is rejected).
- `managementPolicy` (property of `Building`) is the environmental policy of the manager: `restoreOnExit` (boolean) and `restoreAfterSeconds` (number). Without it nothing is restored. How the environment applies it is described in section 3, "Environmental policy".

## 3. Discovery and binding protocol

Executed once, when the person enters the environment:

1. **Locate**: broker endpoint from configuration.
2. **Authenticate**: the agent gets a token. Its scope (zones and operations) is fixed by the environment (`broker.agents[...].scopeZones` in the scenario); the agent cannot widen it.
3. **Enumerate**: the agent asks the environment to follow the person. The environment identifies the person's zone from the positioning signals it receives (strongest beacon, no smoothing), arms triggers on the adjacent zones inside the scope and returns the zone with its adjacent zones (each with its adjacency). When a trigger fires (a reading from an armed zone is the strongest), the environment re-arms around the new zone and pushes the new neighbourhood to the agent before the signal that fired it. Zones outside the scope are never armed.
4. **Subscribe**: positioning signals of the person's zone and of the armed zones are pushed to the agent (R13), so re-planning stays event driven.

Output: a **bound session** = endpoint, token, granted scope, the person's zone and its neighbourhood (updated on trigger), active subscription. The engine enters `Perceive` only after a session is bound. Localization keeps a local adjacency that is the union of the neighbourhoods received so far (it never shrinks), so a trigger of the environment and a zone change of the agent's own estimator cannot race.

**The capability catalogue is not built at binding.** At the start of the `Plan` state, after the request has been interpreted, the engine asks the environment (`listDevices`) for the devices that offer the intent's `controlledProperty` in the zones the intent concerns: the person's zone (or `targetZoneId`) for scope `current_zone`; the person's zone and the adjacent zones ahead for scope `path`; one call without `zoneId` for scope `environment`. The environment decides what to list, within the scope. The answer is used for that plan only; after a zone change (T9) `Plan` asks again for the new zone. An empty answer means capability absent: T5, no command.

**Environmental policy.** The building's `managementPolicy` belongs to the manager of the environment, so the environment applies it; the agent stays a client and never restores anything itself. With `restoreOnExit` true:

- For each token the environment remembers the devices changed by a successful `invokeCommand`, grouped by the device's zone (`refZone`).
- When the person it follows is placed outside such a zone (its own placement, from the positioning signals), a countdown starts; when the person has been outside continuously for `restoreAfterSeconds` (measured on the time of the positioning signals), the environment sets those devices to their `defaultState`. Coming back into the zone before then cancels the countdown; leaving again starts a new one.
- When the token's subscription is closed (the person leaves the building or the session ends), every device the token changed and that is not yet restored is restored at once.
- A device already in its `defaultState` is not touched and not reported; a device that another token has also changed is left to that token.
- Each restoration is notified to the client through the bound session (`on_restoration`): device, zone, restored state, reason (`person_left_zone` or `subscription_closed`), time. The engine does not change state for it and no event record is written: the record schema (C4) and the record count are unchanged. If the person comes back to a zone whose devices were restored, the plan is recomputed as for any zone change (T9) and the devices are commanded again.
- The delay absorbs the flicker of the environment's own placement at a doorway (it has no smoothing): see DECISIONS.md, "Environmental policy".

**Interpretation is a service of the environment.** In the Interpret state the engine sends the request text, its language, the agent's ZoneEstimate and the recent history to the environment (`BoundSession.interpret`, i.e. `EnvironmentBackend.interpret(token, ...)`). The environment builds the GroundingRequest from its own catalogue and adjacency for the token's scope (every zone of the scope with its devices, and the adjacency of those zones plus the entry of each outside zone bordering them), calls the grounder it was configured with (keyword, embedding or LLM), checks the answer against that catalogue (a property no device of the scope offers, or a named zone outside the scope, becomes `unsupported`) and returns the GroundingResult. A ZoneEstimate outside the scope is refused (`out_of_scope`) without interpreting. The agent never receives the catalogue: it learns devices only from `listDevices` in Plan. This is not a device operation: the four operations of section 5 and their allow-list are unchanged. The frozen evaluation runs the grounders itself, on the same GroundingRequest, and reads the catalogue through evaluation-only properties of the bound session. See DECISIONS.md, "Interpretation as a service of the environment".

**Several actions in one message.** If the environment refuses a whole message or asks a clarification about it, the engine cuts the text on the conjunctions and separators of its language (English "and", "then", ","; Italian "e", "poi", ","; at most three parts) and asks the environment to interpret each part. The parts that give an intent are carried out one after the other, each as its own request cycle (Perceive -> Interpret -> Plan -> Act -> Observe -> Perceive, with its records); the user gets one reply saying which parts were done and which were not, and why. A message understood as a whole is never split. Not split or not carried out: a whole message refused as `out_of_scope`, a message with any part refused as `out_of_scope` (the original answer stands), and a message with a part that asks to be followed (`following`): the user is asked to send that part on its own (recorded as Interpret -> Recover, `split:following_not_combined`). If no part gives an intent, the answer for the whole message stands.

## 4. Internal data structures

- **ZoneEstimate**: `zoneId`, `confidence` in [0,1], `observedAt`, optional `previousZoneId`.
- **StructuredIntent**: `action` (verb), `controlledProperty`, `scope` (current zone | path | whole environment), `persistence` (one-off | follows user), `confidence`. `scope` + `persistence` distinguish "turn on the light here" from "I want to walk in the light".
- **ActionPlan**: ordered steps, each = target device, command, guard condition (typically "user arrives in zone X"); plus `validFor` = the ZoneEstimate the plan was computed against.

## 5. Action interface - the action space T

| Operation | Parameters | Returns |
|---|---|---|
| `listZones` | - | the person's zone and its adjacent zones (the neighbourhood the environment follows), with adjacency |
| `listDevices` | `zoneId` (optional), `controlledProperty` (optional) | devices with supported commands, zone and `defaultState`; no `zoneId` = every zone of the granted scope, no `controlledProperty` = every property |
| `getDeviceState` | `deviceId` | current state and `defaultState` |
| `invokeCommand` | `deviceId`, `command`, `value` | outcome, resulting state |

Only `invokeCommand` changes the environment; the other three are observations. (The environment itself also changes devices when it applies the management policy, section 3; that is not an operation of the agent.) The `defaultState` returned by `listDevices` is not given to the grounders: the environment's interpreter receives only `deviceId`, `category`, `controlledProperty` and `supportedCommand`, so the GroundingRequest is unchanged. Interpretation is a separate service of the environment (section 3), not a fifth operation. The zone estimate is NOT an environment action (it comes from Localization through R5/R6). The Environment Interface rejects any call outside this set (allow-list in code). The environment is the authority on scope: it refuses any call outside the granted scope whatever the agent has checked; the Scope Guard and the allow-list in the agent are defence in depth only.

## 6. State machine transitions (Table 5.3)

States: Perceive, Interpret, Plan, Act, Observe, Recover. Parameters: confidence threshold `theta`, `STEP_LIMIT`, `RETRY_LIMIT` (config, defaults 0.6 / 8 / 2).

| From | Trigger | Guard | To |
|---|---|---|---|
| Perceive | Request received | Session bound | Interpret |
| Interpret | ZoneEstimate available | confidence >= theta | Plan |
| Interpret | ZoneEstimate available | confidence < theta | Recover |
| Plan | Plan produced | Plan non-empty | Act |
| Plan | No applicable step | Capability absent | Recover |
| Act | Command invoked | Step count < limit | Observe |
| Act | Command invoked | Step count >= limit | Recover |
| Observe | Outcome received | Intent satisfied | Perceive |
| Observe | Outcome received | `validFor` stale | Plan |
| Observe | Command failed | Retries < limit | Act |
| Observe | Command failed | Retries >= limit | Recover |
| Recover | Fallback applied | - | Perceive |

Notes:
- Intent Grounding (R7/R8) happens inside **Interpret**, as a call to the environment's interpretation service (the intent is computed once per request and reused when re-planning). A message with several actions runs one cycle per understood part.
- The replies to the user are fixed sentences in the language of the request (English or Italian); a refusal is explained in words ("I can't do that: there is no device for the temperature in hallway."), never as a reason code.
- The LLM is used in two places only: Intent Grounding and the *Plan* state (in this prototype the Plan state is rule-based, because the grounded intent + catalogue + adjacency make planning deterministic; see DECISIONS.md).
- Re-planning is triggered by an inspectable condition (`validFor` stale), not by the model's choice.
- Each row has an id (T1..T12 in table order); the event record stores which row fired in `guard`.
- No path through the table allows unbounded cycling; the tests check this (step limit, retry limit).

## 7. Event record (Event Recording section)

One record per transition (exactly one):

| Field | Content |
|---|---|
| `seq` | position in the chain, strictly increasing, no gaps (from 1) |
| `time` | time of the transition (ISO 8601 UTC) |
| `session` | id of the bound session |
| `from`, `to` | source/target state |
| `guard` | transition rule that fired (T1..T12) |
| `zone` | ZoneEstimate in force |
| `intent` | StructuredIntent in force, if any |
| `action` | operation invoked with arguments, if any |
| `outcome` | result of the operation or the reason for recovery |

Commitment and chaining (SHA-256, `||` = concatenation):
- `c_i = H(s_i || enc(r_i))` with fresh random salt `s_i` per record and `enc` = canonical JSON (sorted keys, no whitespace, UTF-8).
- `h_i = H(h_{i-1} || c_i || i)`, `h_0 = H(session)`.
- Local store keeps `r_i, s_i, c_i, h_i` (JSONL, append-only). Records/salts never leave the agent.
- Verification: recompute `c_i`, `h_i` for every record and compare; detect altered, removed, reordered records.
- Erasure: delete `r_i`, `s_i`, keep `c_i`, `h_i`; the rest of the chain still verifies; position `i` is reported as *erased*.
- (Designed in the thesis, not part of the prototype) batches of N links / T seconds -> Merkle root -> anchoring contract `anchor(session,k,a_k,b_k,R_k)` rejecting non-contiguous ranges (`a_k = b_{k-1}+1`); `getAnchor`, `latestBatch`. Private Besu network, QBFT.
- Recording is asynchronous: no transition waits for the log.

## 8. Reference scenario (Fig. "sequence")

User: "I want to walk in the light" ->
R2 request -> R5 zone query -> `{hallway, 0.87}` -> R7 (request, zone) to the environment's interpretation service -> R8 `{activate, light, path, following}` ->
Plan: R12 `listDevices(hallway, light)`, `listDevices(corridor, light)`, `listDevices(kitchen, light)` -> hallway lamp now, corridor lamp on arrival -> R12 `invokeCommand(lamp_hallway, on)` -> result ->
environment trigger on `corridor` (new neighbourhood pushed) -> position signal -> R13 -> R6 zone changed -> `corridor` -> `validFor` stale => Observe -> Plan (asks again around `corridor`); next step fires.
Intent is **reused**, only the plan is revised. The catalogue queries do not add event records: the reference run still has eleven.
Policy: 12 s after the environment has placed the user outside the hallway, it switches `lamp_hallway` back to its default (off) and tells the agent; no record is added. The corridor lamp follows 12 s after the user has left the corridor.
