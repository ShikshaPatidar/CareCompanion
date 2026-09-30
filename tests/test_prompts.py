from pathlib import Path

import pytest

from carecompanion.agents.prompts import PromptLibrary
from carecompanion.domain.errors import ConfigError

NAMES = [
    "coordinator",
    "records_specialist",
    "scheduling_specialist",
    "policy_agent",
    "discharge_extractor",
    "discharge_writer",
]


@pytest.fixture()
def library(settings, profile):
    return PromptLibrary(settings.prompts_dir, profile.prompt_variables())


@pytest.mark.parametrize("name", NAMES)
def test_every_prompt_renders_with_no_leftover_placeholders(library, name):
    text = library.render(name)
    assert "$" not in text and text.strip()


def test_hospital_facts_come_from_config_not_prompt_text(library, profile):
    text = library.render("coordinator")
    assert profile.name in text and profile.contacts["emergency"] in text
    assert profile.contacts["ward_advice_line"] in text
    assert "911" not in text and "Northfield" not in text


def test_writer_prompt_ends_with_the_configured_contact_line(library, profile):
    assert profile.contacts["ward_advice_line"] in library.render("discharge_writer")


def test_undefined_variable_fails_fast(tmp_path):
    (tmp_path / "x.md").write_text("Call $missing_number")
    with pytest.raises(ConfigError):
        PromptLibrary(tmp_path, {}).render("x")


def test_missing_file_is_a_config_error(tmp_path: Path):
    with pytest.raises(ConfigError):
        PromptLibrary(tmp_path, {}).render("nope")
