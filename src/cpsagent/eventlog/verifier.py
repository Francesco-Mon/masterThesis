"""Verifier: recomputes every commitment and link of a stored chain (SPEC section 7).

For each line i (from 1), with h_0 = H(session):
  - kept record:   c_i is recomputed from the stored salt and record and compared with the
                   stored commitment (detects an altered record or salt); `seq` must be i
                   and `session` the expected one;
  - erased record: c_i cannot be recomputed; the stored commitment is taken as is;
  - every line:    h_i = H(h_{i-1} || c_i || i) is recomputed and compared with the stored
                   link (detects removed, inserted, reordered lines, or an altered commitment).
The chain continues from the *stored* link, so each error is reported where it happens.

What the local chain cannot detect alone: removal of the last records (truncation), and an
attacker who rewrites the records *and* recomputes every commitment and link. Both are
caught only by comparing the head with a value kept elsewhere (`expected_head`), which is
the role of ledger anchoring (R17, designed in the thesis, not implemented).
"""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from cpsagent.contracts import StoredRecord

from .chain import commitment, genesis, link
from .store import EventStore


@dataclass
class VerificationReport:
    length: int = 0
    erased: list[int] = field(default_factory=list)  # positions erased (not an error)
    errors: list[tuple[int, str]] = field(default_factory=list)  # (position, kind)
    head: str | None = None  # last stored link

    @property
    def ok(self) -> bool:
        return not self.errors


def verify(
    store: EventStore | str | Path, session: str, expected_head: str | None = None
) -> VerificationReport:
    lines = (store if isinstance(store, EventStore) else EventStore(store)).lines()
    report = VerificationReport(length=len(lines))
    previous = genesis(session)
    for i, line in enumerate(lines, start=1):
        try:
            stored = StoredRecord.model_validate(line)
        except ValidationError:
            report.errors.append((i, "malformed"))
            return report  # no commitment or link to continue from
        if stored.erased:
            report.erased.append(i)
        else:
            if commitment(stored.salt, line["record"]) != stored.commitment:
                report.errors.append((i, "commitment_mismatch"))
            if stored.record.seq != i:
                report.errors.append((i, "seq_mismatch"))
            if stored.record.session != session:
                report.errors.append((i, "session_mismatch"))
        if link(previous, stored.commitment, i) != stored.link:
            report.errors.append((i, "link_mismatch"))
        previous = stored.link
    report.head = previous if lines else None
    if expected_head is not None and report.head != expected_head:
        report.errors.append((len(lines), "head_mismatch"))
    return report
