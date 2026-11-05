"""Local event store: one JSONL line per record, `{"record", "salt", "commitment", "link"}`
(the StoredRecord contract, C4). The line number (from 1) is the position `i` of the chain.

Append-only, with one exception: erasure, which nulls `record` and `salt` of one line and
keeps `commitment` and `link`. It rewrites the file atomically (temporary file + rename),
so a crash never leaves a half-erased store.
"""

import json
import os
import threading
from pathlib import Path
from typing import Any


class EventStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()  # appends (log worker) and erasures may race

    def append(self, line: dict[str, Any]) -> None:
        text = json.dumps(line, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
            f.flush()

    def lines(self) -> list[dict[str, Any]]:
        """Raw stored lines, in order (the verifier works on these, not on parsed models)."""
        with self._lock:
            text = self.path.read_text(encoding="utf-8")
        return [json.loads(row) for row in text.splitlines() if row.strip()]

    def erase(self, position: int) -> None:
        """Delete record and salt at `position` (from 1); commitment and link stay."""
        with self._lock:
            rows = self.path.read_text(encoding="utf-8").splitlines()
            if not 1 <= position <= len(rows):
                raise IndexError(f"no record at position {position}")
            line = json.loads(rows[position - 1])
            line["record"], line["salt"] = None, None
            rows[position - 1] = json.dumps(line, ensure_ascii=False, separators=(",", ":"))
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text("\n".join(rows) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
