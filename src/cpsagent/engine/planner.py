"""Rule-based planner (Plan state): StructuredIntent + zone + catalogue + adjacency -> ActionPlan.

Planning is deterministic once the intent is grounded, so no LLM is used here (SPEC
section 6 allows it; see DECISIONS.md). The rules:

1. Target zones from `scope`:
     current_zone  the user's zone (or `targetZoneId` when the user named another zone), now
     path          the user's zone now, then every adjacent zone except the one the user
                   came from (`previousZoneId`, i.e. the direction of travel) on arrival
     environment   every catalogued zone, now
2. In each target zone, every device whose `controlledProperty` is the intent's property.
3. The command from COMMAND_RULES[(category, action)] (for `set`: SET_COMMANDS[category]
   with the intent's `value`), kept only if the device lists it in its `supportedCommand`
   (catalogue), never assumed.

A step the device cannot perform is dropped, so the plan may be empty: that is how the
planner says "no applicable step" (T5).
"""

from cpsagent.contracts import (
    Action,
    ActionPlan,
    NowGuard,
    OnEnterZoneGuard,
    PlanStep,
    Scope,
    StructuredIntent,
    ZoneCatalogue,
    ZoneEstimate,
)
from cpsagent.contracts.plan import CommandValue, StepGuard

# (device category, action) -> (command, value). Relative actions use fixed values;
# `set` takes the intent's value (SET_COMMANDS); `query` (observation, not actuation) is
# not planned and ends in T5.
COMMAND_RULES: dict[tuple[str, Action], tuple[str, CommandValue]] = {
    ("lamp", Action.ACTIVATE): ("on", None),
    ("lamp", Action.DEACTIVATE): ("off", None),
    ("lamp", Action.INCREASE): ("on", None),
    ("lamp", Action.DECREASE): ("dim", 30),
    ("blind", Action.ACTIVATE): ("close", None),  # shading on = blind closed
    ("blind", Action.DEACTIVATE): ("open", None),
    ("blind", Action.INCREASE): ("close", None),
    ("blind", Action.DECREASE): ("open", None),
    ("thermostat", Action.INCREASE): ("setSetpoint", 23),
    ("thermostat", Action.DECREASE): ("setSetpoint", 19),
}

# device category -> command that takes the `value` of a `set` intent. The value is in
# the property's unit (brightness %, shading %, degrees Celsius); a blind's position is
# % *open*, so shading s becomes position 100 - s.
SET_COMMANDS: dict[str, str] = {
    "lamp": "dim",
    "blind": "setPosition",
    "thermostat": "setSetpoint",
}


def _target_zones(
    intent: StructuredIntent,
    zone: ZoneEstimate,
    catalogue: list[ZoneCatalogue],
    adjacency: dict[str, list[str]],
) -> list[tuple[str, StepGuard]]:
    now = NowGuard()
    if intent.scope == Scope.CURRENT_ZONE:
        return [(intent.target_zone_id or zone.zone_id, now)]
    if intent.scope == Scope.PATH:
        ahead = [z for z in adjacency.get(zone.zone_id, []) if z != zone.previous_zone_id]
        return [(zone.zone_id, now)] + [(z, OnEnterZoneGuard(zone_id=z)) for z in ahead]
    return [(c.zone_id, now) for c in catalogue]


def make_plan(
    intent: StructuredIntent,
    zone: ZoneEstimate,
    catalogue: list[ZoneCatalogue],
    adjacency: dict[str, list[str]],
) -> ActionPlan:
    by_zone = {c.zone_id: c.devices for c in catalogue}  # zones out of scope are absent
    steps = []
    for zone_id, guard in _target_zones(intent, zone, catalogue, adjacency):
        for device in by_zone.get(zone_id, []):
            if device.controlled_property != intent.controlled_property:
                continue
            if intent.action == Action.SET:
                command = SET_COMMANDS.get(device.category)
                value = intent.value
                if device.category == "blind" and value is not None:
                    value = 100 - value
                rule = None if command is None else (command, value)
            else:
                rule = COMMAND_RULES.get((device.category, intent.action))
            if rule is None or rule[0] not in device.supported_command:
                continue
            command, value = rule
            steps.append(
                PlanStep(device_id=device.device_id, command=command, value=value, guard=guard)
            )
    return ActionPlan(steps=steps, valid_for=zone)


def explain_no_step(
    intent: StructuredIntent, zone: ZoneEstimate, catalogue: list[ZoneCatalogue]
) -> str:
    """Reason recorded for T5: no device offers the property where it is needed now
    (capability_absent), or one does but lacks the command (command_absent)."""
    if intent.scope == Scope.ENVIRONMENT:
        zones = {c.zone_id for c in catalogue}
    else:
        zones = {intent.target_zone_id or zone.zone_id}
    offered = any(
        d.controlled_property == intent.controlled_property
        for c in catalogue
        if c.zone_id in zones
        for d in c.devices
    )
    return "command_absent" if offered else "capability_absent"
