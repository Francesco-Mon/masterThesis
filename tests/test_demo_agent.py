"""The engine demo runs offline end to end and its log verifies."""

import sys

from cpsagent import demo_agent


def test_demo_agent_runs(monkeypatch, capsys, tmp_path):
    log = tmp_path / "demo.jsonl"
    monkeypatch.setattr(sys, "argv", ["demo_agent", "--log", str(log)])
    demo_agent.main()
    out = capsys.readouterr().out
    assert "T9   Observe   -> Plan" in out and "[zone_changed]" in out
    assert "invokeCommand(lamp_corridor, on)" in out
    assert "listDevices(zone=corridor, light) -> ['lamp_corridor']" in out  # asked in Plan
    assert "environment: person in corridor" in out  # trigger of the environment
    assert "11 records" in out
    # management policy: the hallway lamp left behind is restored by the environment
    assert "environment restored lamp_hallway to default" in out
    assert "(person left hallway)" in out
    assert "'lamp_hallway': 'off', 'lamp_corridor': 'on', 'lamp_office': 'on'" in out
    assert "Pending restoration: lamp_corridor (corridor), due" in out
    assert "chain VERIFIED" in out and log.exists()
