"""The .NET service reads hospital.json, generated from config/hospital.toml.

If someone edits the TOML and forgets to regenerate, this test fails, so the two
implementations can never silently disagree about opening hours or departments.
"""

import json

from carecompanion.cli import API_CONFIG_PATH


def test_dotnet_hospital_json_matches_the_toml(settings, profile):
    committed = json.loads((settings.project_root / API_CONFIG_PATH).read_text(encoding="utf-8"))
    assert committed == profile.to_api_config(), "Run: carecompanion export-api-config"
