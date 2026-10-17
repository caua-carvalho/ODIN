"""Shared pytest configuration for the backend test suite.

Two jobs:

* register the ``provider_real`` marker used by the opt-in provider contract
  suite (``test_provider_contract.py``);
* snapshot the *real* provider credentials **before any test module runs**.

The second job matters: several test modules set placeholder credentials into
``os.environ`` at import time (``GEMINI_API_KEY=test-key`` in
``test_litellm_provider.py`` and friends). Reading ``os.environ`` from the
contract suite would then mistake a placeholder for a real key and attempt a
network call. ``conftest.py`` is imported before test modules, so the snapshot
below sees only what the developer actually exported.
"""

from __future__ import annotations

import os

import pytest

# Credentials the opt-in provider contract suite needs, plus the opt-in switch.
CONTRACT_ENV_VARS = (
    "ODIN_CONTRACT_TESTS",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OLLAMA_BASE_URL",
)

# Captured at import time — before any test module mutates the environment.
REAL_ENV: dict[str, str] = {
    name: os.environ.get(name, "") for name in CONTRACT_ENV_VARS
}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "provider_real: opt-in integration test that calls a real LLM provider "
        "(requires ODIN_CONTRACT_TESTS to name the provider and that provider's "
        "credential/base URL to be set)",
    )


@pytest.fixture
def real_provider_env() -> dict[str, str]:
    """The real-provider environment, as it was before test modules ran."""
    return dict(REAL_ENV)
