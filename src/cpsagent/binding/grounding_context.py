"""TEMPORARY grounding context: the catalogue and adjacency the frozen grounders take as input.

Why it exists. In the protocol of the thesis the catalogue is not built at binding: the
engine asks the environment for it in the Plan state, after interpretation (listDevices).
The grounders of the evaluation, however, take the catalogue and the adjacency as input
(GroundingRequest), because the frozen evaluation includes off-catalogue requests and
moving the catalogue after interpretation would change the component under evaluation.
Until the grounders are made independent of it, this function builds that input from the
environment, right before interpretation, never at binding. It is the only caller of the
environment's `describe_scope`, which is not one of the four operations of the Interface.
See docs/DECISIONS.md, "Temporary grounding context".

The adjacency must stay identical to the one the evaluation was tuned with, which also has
an entry for each zone outside the scope that borders the scope (the server room). The
environment never lists such a zone; the entry is rebuilt on the agent side from the
adjacency lists of the zones inside the scope, which name it. Two limits: this relies on
adjacency being symmetric (the scenario loader checks it), and the rebuilt entry lists
only neighbours inside the scope (an outside zone bordering another outside zone would get
an incomplete entry; it does not happen in the reference scenario).
"""

from dataclasses import dataclass

from cpsagent.contracts import DeviceDescriptor, ZoneCatalogue
from cpsagent.environment import EnvironmentBackend


@dataclass(frozen=True)
class GroundingContext:
    catalogue: list[ZoneCatalogue]  # every zone of the scope, in the environment's order
    adjacency: dict[str, list[str]]  # zones of the scope, then outside zones that border it

    def catalogue_properties(self) -> set[str]:
        return {d.controlled_property for z in self.catalogue for d in z.devices}

    def catalogue_zones(self) -> set[str]:
        return {z.zone_id for z in self.catalogue}


def temporary_grounding_context(backend: EnvironmentBackend, token: str) -> GroundingContext:
    """Grounding input from `describe_scope` (temporary, see the module docstring)."""
    described = backend.describe_scope(token)
    in_scope = [z.zone_id for z in described.zones]
    catalogue = [
        ZoneCatalogue(
            zone_id=zone_id,
            devices=[
                DeviceDescriptor(
                    device_id=d.device_id,
                    category=d.category,
                    controlled_property=d.controlled_property,
                    supported_command=list(d.supported_command),
                )
                for d in described.devices
                if d.ref_zone == zone_id
            ],
        )
        for zone_id in in_scope
    ]
    adjacency = {z.zone_id: list(z.adjacency) for z in described.zones}
    for zone in described.zones:  # outside zones named by the scope, rebuilt by symmetry
        for other in zone.adjacency:
            if other not in in_scope:
                adjacency.setdefault(other, []).append(zone.zone_id)
    return GroundingContext(catalogue, adjacency)
