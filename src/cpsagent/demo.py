"""Offline demo of the emulated environment: binding, triggers, localization, interface.

Run: python -m cpsagent.demo [--path walk_in_the_light|doorway_linger] [--seed 0]
"""

import argparse

from cpsagent.binding import EnvironmentBinding
from cpsagent.environment import EmulatedEnvironment
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", default="walk_in_the_light")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    env = EmulatedEnvironment()
    path = env.scenario.paths[args.path]
    session = EnvironmentBinding({env.endpoint: env}).bind(
        env.endpoint, "person-agent", path.subject
    )
    print(f"Bound session {session.session_id} at {session.endpoint} (agent {session.agent_id})")
    print(f"Scope granted by the environment: {sorted(session.scope_zones)}")
    print(f"Person's zone known to the environment: {session.neighbourhood.zone_id or 'not yet'}")
    print("No catalogue at binding: the engine asks for devices in the Plan state.\n")

    print(f"Walking path '{args.path}' (seed {args.seed}).")
    print("  [env] = a trigger of the environment fired; plain lines = R6 zone_changed events")
    estimator = ZoneEstimator(dict(session.known_adjacency), path.subject)
    session.on_neighbourhood(lambda n: estimator.add_adjacency(n.adjacency))
    session.on_neighbourhood(
        lambda n: print(f"  [env] person in {n.zone_id}, armed {', '.join(n.armed)}")
    )
    session.subscription.add_listener(estimator.on_signal)
    estimator.subscribe(
        lambda e: print(
            f"  {e.estimate.observed_at:%H:%M:%S}  {e.estimate.previous_zone_id or '-':>9}"
            f" -> {e.estimate.zone_id:<9} confidence {e.estimate.confidence:.2f}"
        )
    )
    ticks = MobilitySimulator(env.scenario, path, seed=args.seed).run(env.publish)
    final = estimator.estimate()
    print(
        f"  final R5 estimate: {final.zone_id} ({final.confidence:.2f}), "
        f"ground truth: {ticks[-1].true_zone}"
    )

    print("\nEnvironment Interface (R12):")
    api = EnvironmentInterface(session)
    calls = [
        {"operation": "listZones", "args": {}},
        {"operation": "listDevices", "args": {"zoneId": "corridor", "controlledProperty": "light"}},
        {"operation": "listDevices", "args": {"controlledProperty": "temperature"}},
        {"operation": "listDevices", "args": {"zoneId": "server_room"}},
        {"operation": "invokeCommand", "args": {"deviceId": "lamp_hallway", "command": "on"}},
        {"operation": "getDeviceState", "args": {"deviceId": "lamp_hallway"}},
        {
            "operation": "invokeCommand",
            "args": {"deviceId": "lamp_corridor", "command": "dim", "value": 40},
        },
        {
            "operation": "invokeCommand",
            "args": {"deviceId": "thermostat_server_room", "command": "setSetpoint", "value": 18},
        },
        {"operation": "deleteDevice", "args": {"deviceId": "lamp_hallway"}},
    ]
    for call in calls:
        result = api.execute(call)
        outcome = result.state if result.ok else f"REJECTED: {result.error}"
        print(f"  {call['operation']}({call['args']})\n      -> {outcome}")


if __name__ == "__main__":
    main()
