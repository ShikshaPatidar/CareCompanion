from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from carecompanion.audit import AuditLog
from carecompanion.config import Settings
from carecompanion.container import build_guards, build_local_gateway, load_hospital

FROZEN_TODAY = date(2026, 9, 28)  # a Monday


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env({})


@pytest.fixture(scope="session")
def profile(settings):
    return load_hospital(settings)


@pytest.fixture()
def gateway(settings, profile, tmp_path: Path):
    """A local scheduling service with isolated state and a frozen clock."""
    return build_local_gateway(
        settings, profile, state_path=tmp_path / "appointments.json", today=lambda: FROZEN_TODAY
    )


@pytest.fixture()
def audit() -> AuditLog:
    return AuditLog(None)


@pytest.fixture(scope="session")
def guards(profile):
    return build_guards(profile)
