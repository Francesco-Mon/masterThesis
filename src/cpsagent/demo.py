"""Offline demo of the emulated environment: binding, catalogue, localization, interface.

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
    print(f"Scope: {sorted(session.scope_zones)}\n")

    print("Capability catalogue (R10):")
    for zone in session.catalogue:
        adjacent = ", ".join(session.spatial_model.adjacency[zone.zone_id])
        print(f"  {zone.zone_id:<13} adjacent to: {adjacent}")
        for d in zone.devices:
            print(f"      {d.device_id:<24} {d.controlled_property:<12} {d.supported_command}")
        if not zone.devices:
            print("      (no devices)")

    print(f"\nWalking path '{args.path}' (seed {args.seed}); R6 zone_changed events:")
    estimator = ZoneEstimator(session.spatial_model.adjacency, path.subject)
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
