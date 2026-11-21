"""Attribution of CPU time and memory to the person's side and the environment's side.

CPU. `CpuAccount` keeps, for every thread, the CPU time of that thread
(`time.thread_time_ns`) charged to named sections: `agent.engine`, `agent.localization`,
`agent.binding`, `agent.interface`, `agent.eventlog` (the record handed to the Event Log
on the agent's thread), `agent.eventlog.writer` (the Event Log's own thread: hashing and
writing), `env.control`, `env.store`,
`env.interpreter`, `harness`. Sections nest: entering a section stops charging the
enclosing one, leaving it resumes; so the time of an environment call made by the engine
goes to the environment, and the time of the agent's Localization called back by the
environment while it delivers a positioning signal goes to the agent. Sections are opened
by wrappers placed exactly where calls cross the agent-environment boundary (the shared
environment's methods, the callbacks the environment calls) and around the components of
the agent (engine, Localization, Interface, the Event Log's writer). Limits: time spent on
threads that open no section (the Orion-LD notification receiver's server threads, the
native threads of torch) is not attributed; it appears as the difference between the
process CPU time (`resource.getrusage`) and the sum of the sections. Python's garbage
collector runs on whichever thread allocates and is charged to the section open there.

Memory. `deep_size` measures the Python objects reachable from an object (the person's
engine, Localization, session; the environment's tables), stopping at shared objects,
functions, classes, modules and enum members. It counts object headers and containers as
`sys.getsizeof` reports them; native memory (model weights, C buffers) is not included and
is measured as resident memory of the process (`RssSampler`, `ps`). `component_of` maps an
allocation's traceback (tracemalloc) to the component of the innermost frame of this
package, for the runs with `--tracemalloc`.
"""

import enum
import resource
import subprocess
import sys
import threading
import time
import types
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

thread_ns = time.thread_time_ns
SECTIONS = (
    "agent.engine",
    "agent.localization",
    "agent.binding",
    "agent.interface",
    "agent.eventlog",
    "agent.eventlog.writer",
    "env.control",
    "env.store",
    "env.interpreter",
    "harness",
)


class _Thread:
    def __init__(self, name: str) -> None:
        self.name = name
        self.stack: list[str] = []
        self.last = 0
        self.totals: dict[str, int] = defaultdict(int)


class CpuAccount:
    def __init__(self) -> None:
        self._local = threading.local()
        self._threads: list[_Thread] = []
        self._lock = threading.Lock()

    def _state(self) -> _Thread:
        state = getattr(self._local, "state", None)
        if state is None:
            state = _Thread(threading.current_thread().name)
            self._local.state = state
            with self._lock:
                self._threads.append(state)
        return state

    def enter(self, section: str) -> None:
        s = self._state()
        now = thread_ns()
        if s.stack:
            s.totals[s.stack[-1]] += now - s.last
        s.stack.append(section)
        s.last = now

    def exit(self) -> None:
        s = self._state()
        now = thread_ns()
        s.totals[s.stack.pop()] += now - s.last
        s.last = now

    @contextmanager
    def section(self, name: str) -> Iterator[None]:
        self.enter(name)
        try:
            yield
        finally:
            self.exit()

    def wrap(self, name: str, fn: Callable) -> Callable:
        def wrapped(*args, **kwargs):
            self.enter(name)
            try:
                return fn(*args, **kwargs)
            finally:
                self.exit()

        return wrapped

    def snapshot(self) -> dict[str, int]:
        """This thread's totals so far (the open section charged up to now)."""
        s = self._state()
        if s.stack:
            now = thread_ns()
            s.totals[s.stack[-1]] += now - s.last
            s.last = now
        return dict(s.totals)

    def totals(self) -> dict[str, int]:
        """Every thread's totals, summed (call when the threads are idle or finished)."""
        out: dict[str, int] = defaultdict(int)
        with self._lock:
            for s in self._threads:
                for k, v in s.totals.items():
                    out[k] += v
        return dict(out)


def delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {k: v - before.get(k, 0) for k, v in after.items() if v - before.get(k, 0)}


def process_cpu_ns() -> int:
    """User + system CPU time of the whole process, every thread included."""
    r = resource.getrusage(resource.RUSAGE_SELF)
    return int((r.ru_utime + r.ru_stime) * 1e9)


def max_rss_bytes() -> int:
    """Peak resident memory of the process (macOS reports bytes, Linux kilobytes)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def rss_bytes(pid: int | None = None) -> int | None:
    """Current resident memory of a process, read with `ps` (no extra dependency)."""
    import os

    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid or os.getpid())],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return int(out) * 1024 if out else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class RssSampler:
    """Resident memory of this process every `period_s`, in a background thread."""

    def __init__(self, period_s: float = 1.0) -> None:
        self.period = period_s
        self.samples: list[tuple[float, int]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="rss-sampler", daemon=True)

    def start(self) -> "RssSampler":
        self._thread.start()
        return self

    def _run(self) -> None:
        start = time.perf_counter()
        while not self._stop.is_set():
            value = rss_bytes()
            if value is not None:
                self.samples.append((round(time.perf_counter() - start, 3), value))
            self._stop.wait(self.period)

    def stop(self) -> list[tuple[float, int]]:
        self._stop.set()
        self._thread.join()
        return self.samples


_SKIP = (
    type,
    types.ModuleType,
    types.FunctionType,
    types.MethodType,
    types.BuiltinFunctionType,
    types.BuiltinMethodType,
    types.CodeType,
    types.FrameType,
    threading.Thread,
    enum.Enum,
)


def deep_size(obj: Any, stop: tuple[Any, ...] = ()) -> int:
    """Bytes of the Python objects reachable from `obj`, each counted once, not entering
    the objects in `stop` (shared ones) nor functions, classes, modules, threads, enums."""
    stop_ids = {id(o) for o in stop}
    seen: set[int] = set()
    total = 0
    todo: list[Any] = [obj]
    while todo:
        o = todo.pop()
        i = id(o)
        if i in seen or i in stop_ids or isinstance(o, _SKIP) or callable(o) and o is not obj:
            continue
        seen.add(i)
        try:
            total += sys.getsizeof(o)
        except TypeError:
            continue
        if isinstance(o, dict):
            todo.extend(o.keys())
            todo.extend(o.values())
        elif isinstance(o, list | tuple | set | frozenset | deque):
            todo.extend(o)
        d = getattr(o, "__dict__", None)
        if isinstance(d, dict):
            todo.append(d)
        for cls in type(o).__mro__:
            for slot in getattr(cls, "__slots__", ()):
                if isinstance(slot, str) and slot not in ("__dict__", "__weakref__"):
                    value = getattr(o, slot, None)
                    if value is not None:
                        todo.append(value)
    return total


# --- tracemalloc ----------------------------------------------------------------------

PACKAGE = str(Path(__file__).resolve().parents[1])  # .../src/cpsagent
_COMPONENTS = (
    ("/engine/", "agent.engine"),
    ("/localization/", "agent.localization"),
    ("/binding/", "agent.binding"),
    ("/interface/", "agent.interface"),
    ("/eventlog/", "agent.eventlog"),
    ("/environment/ngsild/", "env.store"),
    ("/environment/store.py", "env.store"),
    ("/environment/", "env.control"),
    ("/grounding/", "env.interpreter"),
    ("/bench/", "harness"),
)


def component_of(traceback) -> str:
    """Component of the innermost frame of this package (contracts skipped: the contracts
    are built by whoever calls them); `other` if no frame of the package is in it."""
    for frame in reversed(list(traceback)):
        name = frame.filename
        if not name.startswith(PACKAGE) or "/contracts/" in name:
            continue
        rel = name[len(PACKAGE) :]
        for prefix, component in _COMPONENTS:
            if rel.startswith(prefix):
                return component
        return "other.cpsagent"
    return "other"


def tracemalloc_by_component(snapshot) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"bytes": 0, "blocks": 0})
    for stat in snapshot.statistics("traceback"):
        c = out[component_of(stat.traceback)]
        c["bytes"] += stat.size
        c["blocks"] += stat.count
    return dict(out)
