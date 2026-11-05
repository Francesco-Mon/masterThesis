"""Test rig: an engine wired to the emulator with a scriptable localization."""

from datetime import UTC, datetime

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import StructuredIntent, ZoneChangedEvent, ZoneEstimate
from cpsagent.engine import EngineConfig, OrchestrationEngine
from cpsagent.environment import EmulatedEnvironment
from cpsagent.grounding import FakeGrounder
from cpsagent.interface import EnvironmentInterface

T0 = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)


class ScriptedLocalization:
    """R5/R6 double: the test decides the zone and when it changes."""

    def __init__(self, zone: str, confidence: float = 0.9, previous: str | None = None):
        self.current = ZoneEstimate(
            zone_id=zone, confidence=confidence, observed_at=T0, previous_zone_id=previous
        )
        self._listeners = []

    def estimate(self):
        return self.current

    def subscribe(self, listener):
        self._listeners.append(listener)

    def move_to(self, zone: str, confidence: float = 0.9):
        self.current = ZoneEstimate(
            zone_id=zone,
            confidence=confidence,
            observed_at=T0,
            previous_zone_id=self.current.zone_id,
        )
        for listener in self._listeners:
            listener(ZoneChangedEvent(estimate=self.current))


def intent(
    action="activate",
    prop="light",
    scope="current_zone",
    persistence="one_off",
    conf=0.9,
    target=None,
    value=None,
):
    return {
        "kind": "intent",
        "intent": StructuredIntent(
            action=action,
            controlled_property=prop,
            scope=scope,
            persistence=persistence,
            confidence=conf,
            target_zone_id=target,
            value=value,
        ),
    }


WALK = "I want to walk in the light"
SCRIPT = {
    WALK: intent(scope="path", persistence="following", conf=0.9),
    "turn on the light": intent(),
    "dim the light": intent(action="decrease"),
    "turn on all the lights": intent(scope="environment"),
    "maybe some light?": intent(conf=0.4),
    "do the thing": {
        "kind": "clarification",
        "question": "What should I do?",
        "reason": "ambiguous_action",
    },
    "play some music": {"kind": "unsupported", "reason": "capability_absent"},
    "make it humid": intent(prop="humidity"),  # a grounder hallucinating a property
    "turn on the kitchen light": intent(target="kitchen"),
    "warm up the server room": intent(action="increase", prop="temperature", target="server_room"),
    "set the office thermostat to 22": intent(
        action="set", prop="temperature", target="office", value=22
    ),
}


class Rig:
    def __init__(
        self, zone="hallway", confidence=0.9, previous="lobby", config=None, recorder=None
    ):
        self.env = EmulatedEnvironment()
        self.session = EnvironmentBinding({self.env.endpoint: self.env}).bind(
            self.env.endpoint, "person-agent", "user-1"
        )
        self.loc = ScriptedLocalization(zone, confidence, previous)
        self.grounder = FakeGrounder(SCRIPT)
        self.replies = []
        self.engine = OrchestrationEngine(
            self.session,
            self.loc,
            self.grounder,
            EnvironmentInterface(self.session),
            config=config or EngineConfig(),
            recorder=recorder,
            notify=self.replies.append,
            clock=lambda: T0,
        )

    @property
    def guards(self):
        return [t.guard.value for t in self.engine.trace]

    def power(self, device_id):
        token = self.env.authenticate("person-agent")
        return self.env.device(token, device_id).state["power"]
