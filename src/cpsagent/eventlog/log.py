"""Event Log (F7, R16): one record per transition, written asynchronously.

The engine calls `submit(fields)`, which only puts the fields on a queue and returns.
A background thread assigns `seq`, validates the C4 EventRecord, draws a fresh salt,
computes commitment and link, and appends the line to the store. `close()` (or leaving
the `with` block) waits until every queued record is written. So no transition waits
for hashing or disk I/O.
"""

import queue
import threading
from typing import Any

from cpsagent.contracts import EventRecord

from .chain import commitment, genesis, link, new_salt
from .store import EventStore

_STOP = object()


class EventLog:
    def __init__(self, store: EventStore, session: str) -> None:
        self.store = store
        self.session = session
        existing = store.lines()  # continue an existing chain of the same session
        self._seq = len(existing)
        self._head = existing[-1]["link"] if existing else genesis(session)
        self.errors: list[Exception] = []  # records that could not be written (bugs)
        self._queue: queue.Queue[Any] = queue.Queue()
        self._closed = False
        self._worker = threading.Thread(target=self._run, name="event-log", daemon=True)
        self._worker.start()

    @property
    def head(self) -> str:
        """Last link written (h_0 for an empty chain). Read it after `flush()`."""
        return self._head

    def submit(self, fields: dict[str, Any]) -> None:
        """Enqueue one transition (EventRecord fields without seq/session). Never blocks."""
        if self._closed:
            raise RuntimeError("event log is closed")
        self._queue.put(fields)

    def flush(self) -> None:
        self._queue.join()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._queue.put(_STOP)
            self._worker.join()

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                self._write(item)
            except Exception as exc:  # keep logging the next records; tests check `errors`
                self.errors.append(exc)
            finally:
                self._queue.task_done()

    def _write(self, fields: dict[str, Any]) -> None:
        seq = self._seq + 1
        event = EventRecord.model_validate({"seq": seq, "session": self.session, **fields})
        record = event.model_dump(mode="json")
        salt = new_salt()
        c = commitment(salt, record)
        h = link(self._head, c, seq)
        self.store.append({"record": record, "salt": salt, "commitment": c, "link": h})
        self._seq, self._head = seq, h
