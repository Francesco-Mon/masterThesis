"""Interpretation service of the environment: what its interpreter (a grounder) is given.

The environment interprets a request on behalf of an agent: it builds the GroundingRequest
from its own catalogue and adjacency for the token's scope, calls the grounder it was
configured with, and checks the answer against that same catalogue. The agent sends the
text, the language, its zone estimate and its recent history, and receives a
GroundingResult; it never sees the catalogue.

The request is built exactly as the agent built it before interpretation moved here (and
as the frozen evaluation builds it), so every grounder gets the same input it was tuned
with:
  - the catalogue lists every zone of the scope, in the scenario's order, each with the
    devices it holds (`deviceId`, `category`, `controlledProperty`, `supportedCommand`;
    never `defaultState`);
  - the adjacency has an entry for every zone of the scope and, rebuilt by symmetry from
    the zones of the scope that name it, one for each zone outside the scope that borders
    it (the server room). An outside zone bordering another outside zone would get an
    incomplete entry; it does not happen in the reference scenario.
"""

from dataclasses import dataclass

from cpsagent.contracts import (
    DeviceDescriptor,
    GroundingResult,
    IntentResult,
    UnsupportedResult,
    ZoneCatalogue,
)

from .backend import ScopeDescription


@dataclass(frozen=True)
class GroundingContext:
    catalogue: list[ZoneCatalogue]  # every zone of the scope, in the environment's order
    adjacency: dict[str, list[str]]  # zones of the scope, then outside zones that border it

    def catalogue_properties(self) -> set[str]:
        return {d.controlled_property for z in self.catalogue for d in z.devices}

    def catalogue_zones(self) -> set[str]:
        return {z.zone_id for z in self.catalogue}


def grounding_context(described: ScopeDescription) -> GroundingContext:
    """Catalogue and adjacency of a scope, in the shape the grounders take."""
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


def checked(result: GroundingResult, context: GroundingContext) -> GroundingResult:
    """The environment never trusts its interpreter: an intent on a property no device of
    the scope offers, or naming a zone outside the scope, becomes `unsupported`."""
    if not isinstance(result, IntentResult):
        return result
    intent = result.intent
    if intent.controlled_property not in context.catalogue_properties():
        return UnsupportedResult(reason="capability_absent")
    if intent.target_zone_id not in context.catalogue_zones() | {None}:
        return UnsupportedResult(reason="out_of_scope")
    return result
