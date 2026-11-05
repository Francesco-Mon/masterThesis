"""Fixtures for engine tests (the rig itself lives in engine_rig.py, importable by tests)."""

import pytest
from engine_rig import Rig


@pytest.fixture
def rig():
    return Rig()
