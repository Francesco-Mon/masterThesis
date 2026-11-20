"""The measurement harness on the in-memory store (offline): it writes raw rows and
metadata, flags warm-ups and measures every phase."""

import json

from cpsagent.bench import backends


def test_harness_writes_raw_rows_and_metadata(tmp_path, capsys):
    out = backends.main(
        ["--store", "memory", "--repeats", "1", "--warmup", "1", "--calls", "1",
         "--out", str(tmp_path)]
    )  # fmt: skip
    rows = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["store"] == "memory" and meta["repeats"] == 1 and meta["warmup"] == 1
    assert meta["rows"] == len(rows) and "broker" not in meta
    assert {r["warmup"] for r in rows} == {True, False}
    assert {r["repeat"] for r in rows if r["warmup"]} == {0}
    measures = {r["measure"] for r in rows}
    assert measures == {"operation", "cycle", "cycle_state", "scenario_run", "signal",
                        "trigger", "zone_change", "restoration"}  # fmt: skip
    operations = {r["operation"] for r in rows if r["measure"] == "operation"}
    assert operations == {"listZones", "listDevices", "getDeviceState", "invokeCommand",
                          "interpret"}  # fmt: skip
    interpret = next(r for r in rows if r.get("operation") == "interpret")
    assert interpret["latency_ns"] == interpret["interpreter_ns"] + interpret["overhead_ns"]
    lamp = [r for r in rows if r["measure"] == "zone_change" and not r["warmup"]]
    assert [r["to"] for r in lamp] == ["hallway", "corridor", "office"]
    assert all(r["lampOn"]["ns"] is not None for r in lamp)
    assert "median" in capsys.readouterr().out


def test_percentile_is_nearest_rank():
    assert backends.percentile(list(range(1, 101)), 95) == 95
    assert backends.percentile([3.0], 95) == 3.0
