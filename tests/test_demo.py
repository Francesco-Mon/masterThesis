"""The emulated-environment demo runs offline: binding, triggers, localization, interface."""

import sys

from cpsagent import demo


def test_demo_runs(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["demo", "--path", "walk_in_the_light"])
    demo.main()
    out = capsys.readouterr().out
    assert "corridor -> office" in out
    assert "REJECTED: command_not_supported" in out
    assert "No catalogue at binding" in out and "catalogue (R10)" not in out
    assert "[env] person in office, armed corridor" in out
    assert "REJECTED: out_of_scope" in out
