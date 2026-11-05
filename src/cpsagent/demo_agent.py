"""Offline end-to-end demo of the Orchestration Engine and event log: "I want to walk in the light".

The user walks the scripted path lobby -> hallway -> corridor -> office. Once Localization
places them in the hallway, they make the request; the FakeGrounder stands for Intent
Grounding. The engine plans hallway lamp now, corridor lamp on arrival, and re-plans at
every zone change without grounding again. Every transition goes to the event log, which
is verified at the end.

Run: python -m cpsagent.demo_agent [--seed 0] [--log logs/demo_agent.jsonl]
                                  [--grounder fake|llm] [--model openai/gpt-oss-120b]

`--grounder llm` uses Grounder A through OpenRouter (needs OPENROUTER_API_KEY in .env;
calls are cached and logged in results/llm_calls.jsonl).
"""

import argparse
from pathlib import Path

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import ToolResult
from cpsagent.engine import OrchestrationEngine, Transition
from cpsagent.environment import EmulatedEnvironment
from cpsagent.environment.mobility import DEFAULT_START, MobilitySimulator
from cpsagent.eventlog import EventLog, EventStore, verify
from cpsagent.grounding import FakeGrounder
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator

REQUEST = "I want to walk in the light"
# What a grounder should return for REQUEST (SPEC section 8).
SCRIPT = {
    REQUEST: {
        "kind": "intent",
        "intent": {
            "action": "activate",
            "controlledProperty": "light",
            "scope": "path",
            "persistence": "following",
            "confidence": 0.9,
        },
    }
}


def describe(t: Transition) -> str:
    zone = f"{t.zone.zone_id} ({t.zone.confidence:.2f})" if t.zone else "-"
    line = f"  {t.time:%H:%M:%S}  {t.guard.value:<4} {t.source:<9} -> {t.target:<9} zone {zone}"
    if t.action is not None:
        a = t.action.args
        line += f"  {t.action.operation}({a.device_id}, {a.command})"
    if isinstance(t.outcome, ToolResult):
        line += f"  -> {t.outcome.state if t.outcome.ok else t.outcome.error}"
    elif t.outcome is not None:
        line += f"  [{t.outcome}]"
    return line


def make_grounder(kind: str, model: str | None):
    if kind == "fake":
        return FakeGrounder(SCRIPT)
    # imported here: the fake demo must not need the `llm` extra
    from cpsagent.grounding.llm import LLMGrounder, default_model
    from cpsagent.grounding.openrouter import OpenRouterClient

    return LLMGrounder(OpenRouterClient(model or default_model()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--log", default="logs/demo_agent.jsonl")
    parser.add_argument("--grounder", choices=["fake", "llm"], default="fake")
    parser.add_argument("--model", default=None, help="OpenRouter model id (--grounder llm)")
    args = parser.parse_args()

    env = EmulatedEnvironment()
    path = env.scenario.paths["walk_in_the_light"]
    session = EnvironmentBinding({env.endpoint: env}).bind(
        env.endpoint, "person-agent", path.subject
    )
    localization = ZoneEstimator(session.spatial_model.adjacency, path.subject)
    session.subscription.add_listener(localization.on_signal)  # R13

    log_path = Path(args.log)
    log_path.unlink(missing_ok=True)  # one demo run = one fresh chain
    store = EventStore(log_path)
    log = EventLog(store, session.session_id)

    now = [DEFAULT_START]  # simulated time, so record times follow the walk

    def record(t: Transition) -> None:
        log.submit(t.record_fields())  # R16: enqueue only
        print(describe(t))

    engine = OrchestrationEngine(
        session,
        localization,
        make_grounder(args.grounder, args.model),
        EnvironmentInterface(session),
        recorder=record,
        notify=lambda r: print(f"  agent says ({r.status}): {r.message}"),
        clock=lambda: now[0],
    )
    print(f"Session {session.session_id}; walking path walk_in_the_light (seed {args.seed})\n")

    asked = False
    for tick in MobilitySimulator(env.scenario, path, seed=args.seed).ticks():
        now[0] = tick.time
        for signal in tick.signals:
            env.publish(signal)  # -> subscription -> Localization -> R6 -> engine
        estimate = localization.estimate()
        if not asked and estimate.zone_id == "hallway" and estimate.confidence >= 0.6:
            print(f'  {tick.time:%H:%M:%S}  user says: "{REQUEST}"')
            engine.handle_request(REQUEST)
            asked = True

    engine.close()  # end of session: the following intent ends (T8)
    log.close()  # flush the queue

    token = env.authenticate("person-agent")
    lamps = {
        d.device_id: env.device(token, d.device_id).state["power"]
        for d in env.scenario.devices
        if d.category == "lamp"
    }
    print(f"\nLamps: {lamps}")
    report = verify(store, session.session_id)
    status = "VERIFIED" if report.ok else f"FAILED {report.errors}"
    print(f"Log {log_path}: {report.length} records, chain {status}, head {report.head[:16]}...")


if __name__ == "__main__":
    main()
