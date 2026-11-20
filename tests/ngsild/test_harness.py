"""The measurement harness on Orion-LD: broker versions in the metadata, the broker's part
of each signal delivery in the rows."""

import json

import pytest

from cpsagent.bench import backends

pytestmark = pytest.mark.ngsild


def test_harness_on_orion_ld(broker_url, tmp_path):
    out = backends.main(
        ["--store", "ngsild", "--url", broker_url, "--repeats", "1", "--warmup", "0",
         "--calls", "1", "--out", str(tmp_path)]
    )  # fmt: skip
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["broker"]["orionLd"] == "1.13.0"
    assert meta["broker"]["mongodbServer"] == "4.4.29"
    rows = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
    signals = [r for r in rows if r["measure"] == "signal"]
    assert signals and all("update_ns" in r and "notification_ns" in r for r in signals)
