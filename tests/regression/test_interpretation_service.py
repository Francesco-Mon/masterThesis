"""Interpretation moved into the environment: the grounder must not notice.

The GroundingRequest the environment's interpreter receives for every dataset case is
compared with the one recorded in `baseline.json` (built on the agent side before the
change, and still built that way by the frozen evaluation). A case whose zone is outside
the scope is refused by the environment before interpretation (no request reaches the
grounder); the request the environment would build for it is still compared.
"""

import pytest
from test_alignment_regression import BASELINE, _sha  # same folder (rootdir import mode)

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import UnsupportedResult
from cpsagent.environment import EmulatedEnvironment, OutOfScopeError
from cpsagent.eval.dataset import load_cases


class Recorder:
    """An interpreter that records the request and answers `unsupported`."""

    def __init__(self):
        self.requests = []

    def ground(self, request):
        self.requests.append(request)
        return UnsupportedResult(reason="capability_absent")


@pytest.fixture(scope="module")
def bound():
    recorder = Recorder()
    env = EmulatedEnvironment(interpreter=recorder)
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    return env, session, recorder


def test_every_case_reaches_the_interpreter_with_the_baseline_request(bound):
    env, session, recorder = bound
    cases, errors = load_cases()
    assert errors == [] and len(cases) == 210
    built, refused = {}, []
    for case in cases:
        zone = case.zone_estimate()
        built[case.id] = _sha(env.grounding_request(session.token, case.text, case.language,
                                                    zone, []))  # fmt: skip
        recorder.requests.clear()
        try:
            session.interpret(case.text, case.language, zone, [])
        except OutOfScopeError:
            refused.append(case.id)
            assert recorder.requests == []  # refused before any grounding
            continue
        assert [_sha(r) for r in recorder.requests] == [BASELINE["groundingRequestSha256"][case.id]]
    assert built == BASELINE["groundingRequestSha256"]  # all 210, refused ones included
    assert len(refused) == 5
    assert {c.zone.zoneId for c in cases if c.id in refused} == {"server_room"}


def test_the_request_carries_the_agent_history(bound):
    env, session, recorder = bound
    recorder.requests.clear()
    cases, _ = load_cases()
    case = next(c for c in cases if c.zone.zoneId == "hallway")
    session.interpret(case.text, case.language, case.zone_estimate(), ["turn on the light"])
    assert recorder.requests[0].history == ["turn on the light"]
