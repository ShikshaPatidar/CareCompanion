import pytest

from carecompanion.config import Settings
from carecompanion.domain.errors import ConfigError


def test_settings_from_env_reads_and_trims():
    s = Settings.from_env(
        {
            "FOUNDRY_PROJECT_ENDPOINT": " https://x/api/projects/p ",
            "FOUNDRY_MODEL_DEPLOYMENT_NAME": "gpt-5-mini",
            "APPOINTMENTS_API_URL": "http://localhost:5080/",
            "AUDIT_LOG_CONTENT": "TRUE",
        }
    )
    assert s.project_endpoint == "https://x/api/projects/p"
    assert s.appointments_api_url == "http://localhost:5080"
    assert s.audit_log_content is True
    assert s.policy_agent_name == "elmfield-policy-agent"


def test_require_foundry_lists_everything_missing():
    with pytest.raises(ConfigError) as err:
        Settings.from_env({}).require_foundry(need_resource_endpoint=True)
    message = str(err.value)
    for name in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_DEPLOYMENT_NAME", "FOUNDRY_RESOURCE_ENDPOINT"):
        assert name in message


def test_profile_loads_and_finds_departments_by_alias(profile):
    assert profile.name == "Elmfield Community Hospital"
    assert profile.find_department("blood test").name == "Phlebotomy (Blood Tests)"
    assert profile.find_department("  CARDIOLOGY ").name == "Cardiology"
    assert profile.find_department("dentistry") is None


def test_allowed_phone_digits_include_contacts(profile):
    allowed = profile.allowed_phone_digits()
    assert "02079460142" in allowed and "999" in allowed
