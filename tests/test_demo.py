"""The emulated-environment demo runs offline and shows localization and catalogue."""

import sys

from cpsagent import demo


def test_demo_runs(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["demo", "--path", "walk_in_the_light"])
    demo.main()
    out = capsys.readouterr().out
    assert "corridor -> office" in out
    assert "REJECTED: command_not_supported" in out
