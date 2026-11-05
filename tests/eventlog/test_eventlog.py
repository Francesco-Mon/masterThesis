"""Event log: commitments + hash chain verify; tampering is detected; erasure keeps the
chain valid; writing is asynchronous."""

import json
import threading
from datetime import UTC, datetime

import pytest

from cpsagent.contracts import TRANSITIONS, Guard
from cpsagent.eventlog import (
    EventLog,
    EventStore,
    canonical,
    commitment,
    genesis,
    link,
    verify,
)

SESSION = "sess-001"
T0 = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)
ZONE = {"zoneId": "hallway", "confidence": 0.87, "observedAt": T0, "previousZoneId": "lobby"}


def fields(guard: Guard, outcome=None):
    source, target = TRANSITIONS[guard]
    return {
        "time": T0,
        "from": source,
        "to": target,
        "guard": guard,
        "zone": ZONE,
        "outcome": outcome,
    }


SEQUENCE = [Guard.T1, Guard.T2, Guard.T4, Guard.T6, Guard.T8, Guard.T1, Guard.T3, Guard.T12]


@pytest.fixture
def store(tmp_path):
    s = EventStore(tmp_path / "log.jsonl")
    with EventLog(s, SESSION) as log:
        for g in SEQUENCE:
            log.submit(fields(g, outcome=f"o{g.value}"))
    assert not log.errors
    return s


def rows(store):
    return store.path.read_text().splitlines()


def rewrite(store, rows_):
    store.path.write_text("\n".join(rows_) + "\n")


def kinds(report):
    return {kind for _, kind in report.errors}


# --- primitives -----------------------------------------------------------------------------


def test_canonical_json_is_independent_of_key_order_and_whitespace():
    assert canonical({"b": 1, "a": "è"}) == canonical(json.loads('{ "a" : "è", "b" : 1 }'))
    assert canonical({"b": 1, "a": "è"}) == '{"a":"è","b":1}'.encode()


def test_same_record_different_salt_gives_unrelated_commitments():
    r = {"seq": 1}
    assert commitment("00" * 32, r) != commitment("01" * 32, r)
    assert len(commitment("00" * 32, r)) == 64


# --- a correct chain ------------------------------------------------------------------------


def test_complete_chain_verifies(store):
    report = verify(store, SESSION)
    assert report.ok and report.length == len(SEQUENCE) and report.erased == []
    lines = store.lines()
    assert [ln["record"]["seq"] for ln in lines] == list(range(1, len(SEQUENCE) + 1))
    assert len({ln["salt"] for ln in lines}) == len(SEQUENCE)  # fresh salt per record
    assert lines[0]["link"] == link(genesis(SESSION), lines[0]["commitment"], 1)
    assert report.head == lines[-1]["link"]


def test_wrong_session_does_not_verify(store):
    assert {"session_mismatch", "link_mismatch"} <= kinds(verify(store, "sess-999"))


# --- tampering ------------------------------------------------------------------------------


def test_altered_record_is_detected_at_its_position(store):
    r = rows(store)
    line = json.loads(r[3])
    line["record"]["outcome"] = "something else"
    r[3] = json.dumps(line)
    rewrite(store, r)
    assert verify(store, SESSION).errors == [(4, "commitment_mismatch")]


def test_removed_record_is_detected(store):
    r = rows(store)
    del r[2]
    rewrite(store, r)
    report = verify(store, SESSION)
    assert not report.ok and report.errors[0][0] == 3
    assert {"seq_mismatch", "link_mismatch"} <= kinds(report)


def test_reordered_records_are_detected(store):
    r = rows(store)
    r[4], r[5] = r[5], r[4]
    rewrite(store, r)
    report = verify(store, SESSION)
    assert not report.ok and report.errors[0][0] == 5
    assert {"seq_mismatch", "link_mismatch"} <= kinds(report)


def test_altered_commitment_breaks_the_link(store):
    r = rows(store)
    line = json.loads(r[1])
    line["commitment"] = "0" * 64
    r[1] = json.dumps(line)
    rewrite(store, r)
    assert (2, "link_mismatch") in verify(store, SESSION).errors


def test_truncation_and_full_rewrite_need_a_known_head(store):
    """Limits of a local chain: dropping the tail, or rewriting a record and recomputing
    everything after it, verifies locally; it fails against a head kept elsewhere
    (what ledger anchoring would provide)."""
    head = verify(store, SESSION).head
    r = rows(store)
    rewrite(store, r[:-2])
    assert verify(store, SESSION).ok
    assert verify(store, SESSION, expected_head=head).errors == [(6, "head_mismatch")]

    rewrite(store, r)
    lines = [json.loads(x) for x in r]
    lines[0]["record"]["outcome"] = "forged"
    previous = genesis(SESSION)
    for i, ln in enumerate(lines, start=1):
        ln["commitment"] = commitment(ln["salt"], ln["record"])
        ln["link"] = previous = link(previous, ln["commitment"], i)
    rewrite(store, [json.dumps(ln) for ln in lines])
    assert verify(store, SESSION).ok
    assert not verify(store, SESSION, expected_head=head).ok


# --- erasure --------------------------------------------------------------------------------


def test_erasure_keeps_the_chain_valid_and_reports_the_position(store):
    before = store.lines()
    store.erase(3)
    after = store.lines()
    assert after[2]["record"] is None and after[2]["salt"] is None
    assert (after[2]["commitment"], after[2]["link"]) == (
        before[2]["commitment"],
        before[2]["link"],
    )
    assert after[:2] + after[3:] == before[:2] + before[3:]
    report = verify(store, SESSION)
    assert report.ok and report.erased == [3]
    store.erase(3)  # idempotent
    store.erase(7)
    assert verify(store, SESSION).erased == [3, 7]


def test_erasure_does_not_hide_later_tampering(store):
    store.erase(2)
    r = rows(store)
    line = json.loads(r[1])
    line["commitment"] = "f" * 64
    r[1] = json.dumps(line)
    rewrite(store, r)
    assert (2, "link_mismatch") in verify(store, SESSION).errors


def test_erasing_a_missing_position_fails(store):
    with pytest.raises(IndexError):
        store.erase(99)


def test_half_erased_line_is_malformed(store):
    r = rows(store)
    line = json.loads(r[0])
    line["salt"] = None  # record kept, salt deleted: not a valid erasure
    r[0] = json.dumps(line)
    rewrite(store, r)
    assert verify(store, SESSION).errors == [(1, "malformed")]


# --- asynchronous writing -------------------------------------------------------------------


class GatedStore(EventStore):
    """A store whose writes block until the test opens the gate (a very slow disk)."""

    def __init__(self, path):
        super().__init__(path)
        self.gate = threading.Event()

    def append(self, line):
        assert self.gate.wait(timeout=5), "gate never opened"
        super().append(line)


def test_submit_does_not_wait_for_the_write_and_close_flushes(tmp_path):
    store = GatedStore(tmp_path / "log.jsonl")
    log = EventLog(store, SESSION)
    for g in SEQUENCE:
        log.submit(fields(g))  # returns immediately although no write can complete
    assert store.lines() == []
    store.gate.set()
    log.close()
    assert len(store.lines()) == len(SEQUENCE) and verify(store, SESSION).ok
    with pytest.raises(RuntimeError):
        log.submit(fields(Guard.T1))


def test_a_reopened_log_continues_the_chain(store):
    with EventLog(store, SESSION) as log:
        log.submit(fields(Guard.T1))
    report = verify(store, SESSION)
    assert report.ok and report.length == len(SEQUENCE) + 1


def test_an_invalid_record_is_reported_not_written(tmp_path):
    store = EventStore(tmp_path / "log.jsonl")
    with EventLog(store, SESSION) as log:
        log.submit({**fields(Guard.T1), "to": "Act"})  # guard does not match the states
        log.submit(fields(Guard.T1))
    assert len(log.errors) == 1 and len(store.lines()) == 1 and verify(store, SESSION).ok
