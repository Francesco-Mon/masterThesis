"""Fixtures for the tests on a running Orion-LD (`docker compose up -d`; `pytest -m ngsild`).

A broker that does not answer fails the tests (they were asked for explicitly), with the
command that starts it.
"""

import os

import httpx
import pytest

from cpsagent.environment.ngsild import DEFAULT_URL, ngsild_environment
from cpsagent.environment.ngsild.seed import seed
from cpsagent.grounding.keyword import KeywordGrounder

URL = os.getenv("NGSILD_URL", DEFAULT_URL)


@pytest.fixture(scope="session")
def broker_url():
    try:
        httpx.get(f"{URL}/version", timeout=3).raise_for_status()
    except httpx.HTTPError as exc:
        pytest.fail(f"Orion-LD not reachable at {URL} ({exc}): run `docker compose up -d`")
    return URL


@pytest.fixture
def orion(broker_url):
    """A freshly seeded broker and a factory of environments on it, closed at the end."""
    made = []

    def make(interpreter=None):
        env = ngsild_environment(broker_url, interpreter or KeywordGrounder())
        made.append(env)
        return env

    seed(broker_url)
    yield make
    for env in made:
        env.close()
