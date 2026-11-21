"""CPU and memory of the Orion-LD and MongoDB containers, sampled during a run.

Reads the Docker Engine API on its Unix socket (`GET /containers/{id}/stats`, streamed:
one sample per second per container), so no `docker stats` process is started per sample.
Each sample keeps the raw counters: cumulative CPU time of the container in nanoseconds
(`cpu_stats.cpu_usage.total_usage`), the memory in use (`memory_stats.usage` minus the
`inactive_file` page cache, as `docker stats` shows it), the memory limit and the number
of processes. CPU seconds over a window are the difference of the cumulative counter
between its first and last sample, so they do not depend on the sampling period.

On Apple silicon the Orion-LD image is amd64 and runs under emulation inside the Docker
Desktop virtual machine: its CPU time includes the emulation.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

SOCKETS = (Path("/var/run/docker.sock"), Path.home() / ".docker" / "run" / "docker.sock")
SERVICES = ("orion", "mongo")


def socket_path() -> Path:
    for path in SOCKETS:
        if path.exists():
            return path
    raise FileNotFoundError("Docker socket not found")


def containers(project: str = "cps-agent") -> dict[str, str]:
    """Compose service name -> container id, for the running services of the project."""
    client = httpx.Client(transport=httpx.HTTPTransport(uds=str(socket_path())), timeout=10)
    filters = json.dumps({"label": [f"com.docker.compose.project={project}"]})
    listed = client.get("http://docker/containers/json", params={"filters": filters}).json()
    client.close()
    return {c["Labels"]["com.docker.compose.service"]: c["Id"] for c in listed}


class ContainerStats:
    def __init__(self, ids: dict[str, str]) -> None:
        self.ids = ids
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._threads = [
            threading.Thread(
                target=self._stream, args=(name, cid), daemon=True, name=f"docker-stats-{name}"
            )  # fmt: skip
            for name, cid in ids.items()
        ]

    def start(self) -> "ContainerStats":
        for t in self._threads:
            t.start()
        return self

    def _stream(self, name: str, cid: str) -> None:
        transport = httpx.HTTPTransport(uds=str(socket_path()))
        with httpx.Client(transport=transport, timeout=None) as client:
            url = f"http://docker/containers/{cid}/stats"
            with client.stream("GET", url, params={"stream": "true"}) as response:
                for line in response.iter_lines():
                    if self._stop.is_set():
                        return
                    if not line.strip():
                        continue
                    s = json.loads(line)
                    mem = s.get("memory_stats", {})
                    inactive = mem.get("stats", {}).get("inactive_file", 0)
                    row = {
                        "t": time.perf_counter(),
                        "container": name,
                        "read": s.get("read"),
                        "cpuTotalNs": s.get("cpu_stats", {})
                        .get("cpu_usage", {})
                        .get("total_usage"),
                        "onlineCpus": s.get("cpu_stats", {}).get("online_cpus"),
                        "memUsedBytes": (mem.get("usage") or 0) - inactive,
                        "memLimitBytes": mem.get("limit"),
                        "pids": s.get("pids_stats", {}).get("current"),
                    }
                    with self._lock:
                        self.samples.append(row)

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)  # the stream yields a sample per second
        with self._lock:
            return list(self.samples)


def window(samples: list[dict[str, Any]], start: float, end: float) -> dict[str, Any]:
    """Per container, over [start, end] (perf_counter seconds): CPU seconds, mean CPU in
    cores, memory median and maximum."""
    out = {}
    for name in sorted({s["container"] for s in samples}):
        rows = [s for s in samples if s["container"] == name and start <= s["t"] <= end]
        if len(rows) < 2:
            out[name] = {"samples": len(rows)}
            continue
        cpu_s = (rows[-1]["cpuTotalNs"] - rows[0]["cpuTotalNs"]) / 1e9
        span = rows[-1]["t"] - rows[0]["t"]
        mem = sorted(r["memUsedBytes"] for r in rows)
        out[name] = {
            "samples": len(rows),
            "spanS": round(span, 3),
            "cpuSeconds": round(cpu_s, 3),
            "cpuCores": round(cpu_s / span, 4) if span else None,
            "memMedianBytes": mem[len(mem) // 2],
            "memMaxBytes": mem[-1],
            "pidsMax": max(r["pids"] or 0 for r in rows),
        }
    return out
