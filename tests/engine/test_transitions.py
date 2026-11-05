"""The transition table is data: same rows as the contract, guards mutually exclusive."""

import itertools

from cpsagent.contracts import TRANSITIONS, Guard, State
from cpsagent.engine import TABLE, Context, EngineConfig, Trigger, select


def test_table_has_rows_t1_to_t12_with_the_contract_states():
    assert [r.id for r in TABLE] == list(Guard)
    for row in TABLE:
        assert (row.source, row.target) == TRANSITIONS[row.id]


def contexts():
    """A grid over every guard input, around the default limits."""
    cfg = EngineConfig()
    for (
        conf_z,
        conf_i,
        step,
        retries,
        applicable,
        changed,
        ended,
        following,
        bound,
    ) in itertools.product(
        [0.0, 0.59, 0.6, 1.0],
        [0.0, 0.6, 1.0],
        [0, 7, 8, 9],
        [0, 1, 2, 3],
        [False, True],
        [False, True],
        [False, True],
        [False, True],
        [False, True],
    ):
        yield Context(
            config=cfg,
            session_bound=bound,
            zone_confidence=conf_z,
            intent_confidence=conf_i,
            has_applicable_step=applicable,
            step_count=step,
            retries=retries,
            zone_changed=changed,
            intent_ended=ended,
            following=following,
        )


def test_guards_are_mutually_exclusive():
    pairs = {(r.source, r.trigger) for r in TABLE}
    for ctx in contexts():
        for state, trigger in pairs:
            select(state, trigger, ctx)  # raises if two rows fire


def test_only_observe_can_wait():
    """In every context some row fires, except Observe on a success (following intent,
    nothing pending, user still in the planned zone) and T1 when the session is not bound
    (the request is rejected before entering the machine). Plan's two rows have their own
    trigger each (T4 / T5), so they are checked together."""
    groups = {}
    for r in TABLE:
        key = (r.source, None) if r.source == State.PLAN else (r.source, r.trigger)
        groups.setdefault(key, set()).add(r.trigger)
    for ctx in contexts():
        for (state, _), triggers in groups.items():
            if any(select(state, t, ctx) for t in triggers):
                continue
            trigger = next(iter(triggers))
            assert (state, trigger) in {
                (State.OBSERVE, Trigger.OUTCOME_RECEIVED),
                (State.PERCEIVE, Trigger.REQUEST_RECEIVED),
            }
            if state == State.OBSERVE:
                assert ctx.following and not ctx.intent_ended
                assert not ctx.has_applicable_step and not ctx.zone_changed
            else:
                assert not ctx.session_bound
