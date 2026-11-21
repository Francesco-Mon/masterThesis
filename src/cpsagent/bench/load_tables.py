"""Summary tables of saved load runs, built from their point.json files only.

Run: python -m cpsagent.bench.load_tables RUN_DIR [RUN_DIR ...] --out results/load/tables

Writes (one row per point of every run, with run, store, interpreter, mode, persons, rate):
  points.csv       throughput, errors, end-to-end latency percentiles, interpretation wait
                   and service, ticks (signals per second, delay), the failure flags
  operations.csv   per environment operation: calls, wait for the environment lock and
                   service time percentiles
  cpu.csv          CPU per request and per signal by section, the agent and environment
                   totals, the Event Log writer per record, process CPU and the part not
                   attributed to a section
  memory.csv       process resident memory (start, maximum), per-person structures (engine,
                   its transitions, Localization, session, Event Log on disk per record),
                   environment tables (follows, armed triggers, change records, pending
                   restorations, latest readings) and their size, tracemalloc by component
  containers.csv   Orion-LD and MongoDB: CPU seconds, mean cores, memory median and maximum
  conflicts.csv    command pairs on one device within the window, contradictory pairs,
                   restorations during the run and those with another person in the zone
Nothing is plotted.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

KEYS = ["run", "store", "interpreter", "mode", "persons", "rate"]


def points(runs: list[Path]):
    for run in runs:
        for path in sorted((run / "points").glob("*/point.json")):
            yield run.name, json.loads(path.read_text())


def key(run: str, s: dict[str, Any]) -> list[Any]:
    return [run, s["store"], s["interpreter"], s["mode"], s["persons"], s["rate"]]


def write(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m cpsagent.bench.load_tables")
    p.add_argument("runs", nargs="+", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list[list[Any]]] = {n: [] for n in
                                       ("points", "operations", "cpu", "memory", "containers",
                                        "conflicts")}  # fmt: skip
    sections: set[str] = set()
    components: set[str] = set()
    data = list(points(args.runs))
    for _, s in data:
        sections |= set(s["cpu"]["perRequestUs"]["bySection"]) | set(
            s["cpu"]["perSignalUs"]["bySection"]
        )
        components |= set((s["memory"].get("tracemalloc") or {}).keys())
    sections_l, components_l = sorted(sections), sorted(components)
    for run, s in data:
        k = key(run, s)
        lat, iw, isv, t = s["latencyMs"], s["interpretWaitMs"], s["interpretServiceMs"], s["ticks"]
        rows["points"].append(k + [
            "+".join(s["failed"]), s["stopReason"], s["measuredS"], s["requests"]["measured"],
            s["requests"]["errors"], s["throughputRps"], lat["p50"], lat["p90"], lat["p95"],
            lat["p99"], lat["max"], lat["mean"], s["serviceMs"]["p95"], s["agentWaitMs"]["p95"],
            (s.get("queueMs") or {}).get("p95"), s["interpretations"], iw["p50"], iw["p95"],
            iw["p99"], isv["p50"], isv["p95"], t["signalsPerS"], t["lagMs"]["p50"],
            t["lagMs"]["p95"], t["lagMs"]["max"], t["publishPerSignalMs"]["p50"],
            t["publishPerSignalMs"]["p95"], t["errors"], s.get("recoveredSignals"),
        ])  # fmt: skip
        for op, d in s["operationsMs"].items():
            w, sv = d["wait"], d["service"]
            rows["operations"].append(k + [op, w["n"], w["p50"], w["p95"], w["p99"], sv["p50"],
                                           sv["p95"], sv["p99"], sv["mean"]])  # fmt: skip
        cpu = s["cpu"]
        rq, sg = cpu["perRequestUs"], cpu["perSignalUs"]
        rows["cpu"].append(
            k
            + [
                rq["agent"],
                rq["environment"],
                sg["agent"],
                sg["environment"],
                cpu["eventLogWriterPerRecordUs"],
                cpu["runProcessS"],
                cpu["runAttributedS"],
                cpu["runUnattributedS"],
                cpu["processCores"],
            ]  # fmt: skip
            + [rq["bySection"].get(x) for x in sections_l]
            + [sg["bySection"].get(x) for x in sections_l]
        )
        m = s["memory"]
        per, env = m["persons"], m["environment"]
        tm = m.get("tracemalloc") or {}
        rows["memory"].append(
            k
            + [
                m["rssStartBytes"],
                m["rssMaxBytes"],
                m["processPeakRssBytes"],
                per["engineBytes"]["mean"],
                per["engineBytes"]["max"],
                per["traceBytes"]["mean"],
                per["trace"]["mean"],
                per["history"]["mean"],
                per["localizationBytes"]["mean"],
                per["sessionBytes"]["mean"],
                per["eventLogMemoryBytes"]["mean"],
                m["eventLogDiskBytes"],
                m["eventLogRecords"],
                m["eventLogBytesPerRecord"],
                env["follows"],
                env["armedTriggers"],
                env["changeRecords"],
                env["pendingRestorations"],
                env["latestReadings"],
                env["subscriptions"],
                sum(env["bytes"].values()),
            ]  # fmt: skip
            + [tm.get(c, {}).get("bytes") for c in components_l]
        )
        for name, c in (s.get("containers") or {}).items():
            rows["containers"].append(k + [name, c.get("samples"), c.get("cpuSeconds"),
                                           c.get("cpuCores"), c.get("memMedianBytes"),
                                           c.get("memMaxBytes"), c.get("pidsMax")])  # fmt: skip
        cf = s["conflicts"]
        rows["conflicts"].append(k + [s["requests"]["measured"], cf["commandPairs"],
                                      cf["contradictoryPairs"], cf["restorationsDuringRun"],
                                      cf["restorationsWithOthersInZone"]])  # fmt: skip

    write(args.out / "points.csv", KEYS + [
        "failed", "stopReason", "measuredS", "requests", "errors", "throughputRps",
        "lat_p50_ms", "lat_p90_ms", "lat_p95_ms", "lat_p99_ms", "lat_max_ms", "lat_mean_ms",
        "service_p95_ms", "agentWait_p95_ms", "queue_p95_ms", "interpretations",
        "interpWait_p50_ms", "interpWait_p95_ms", "interpWait_p99_ms", "interpService_p50_ms",
        "interpService_p95_ms", "signalsPerS", "tickLag_p50_ms", "tickLag_p95_ms",
        "tickLag_max_ms", "publishPerSignal_p50_ms", "publishPerSignal_p95_ms", "tickErrors",
        "recoveredSignals",
    ], rows["points"])  # fmt: skip
    write(args.out / "operations.csv", KEYS + [
        "operation", "calls", "wait_p50_ms", "wait_p95_ms", "wait_p99_ms", "service_p50_ms",
        "service_p95_ms", "service_p99_ms", "service_mean_ms",
    ], rows["operations"])  # fmt: skip
    write(args.out / "cpu.csv", KEYS + [
        "req_agent_us", "req_env_us", "sig_agent_us", "sig_env_us", "eventlog_writer_record_us",
        "process_s", "attributed_s", "unattributed_s", "process_cores",
    ] + [f"req_{x}_us" for x in sections_l] + [f"sig_{x}_us" for x in sections_l],
        rows["cpu"])  # fmt: skip
    write(args.out / "memory.csv", KEYS + [
        "rss_start_bytes", "rss_max_bytes", "peak_rss_bytes", "engine_bytes_mean",
        "engine_bytes_max", "trace_bytes_mean", "transitions_mean", "history_mean",
        "localization_bytes_mean", "session_bytes_mean", "eventlog_memory_bytes_mean",
        "eventlog_disk_bytes", "eventlog_records", "eventlog_bytes_per_record", "env_follows",
        "env_armed_triggers", "env_change_records", "env_pending_restorations",
        "env_latest_readings", "env_subscriptions", "env_tables_bytes",
    ] + [f"tracemalloc_{c}_bytes" for c in components_l], rows["memory"])  # fmt: skip
    write(args.out / "containers.csv", KEYS + [
        "container", "samples", "cpu_seconds", "cpu_cores", "mem_median_bytes",
        "mem_max_bytes", "pids_max",
    ], rows["containers"])  # fmt: skip
    write(args.out / "conflicts.csv", KEYS + [
        "requests", "command_pairs", "contradictory_pairs", "restorations_during_run",
        "restorations_with_others_in_zone",
    ], rows["conflicts"])  # fmt: skip
    print(f"{len(data)} points -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
