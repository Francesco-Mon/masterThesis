"""Smoke test: the package is importable from the virtual environment."""

import cpsagent


def test_package_imports():
    assert cpsagent.__version__
