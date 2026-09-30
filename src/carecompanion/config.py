"""Runtime settings, read once from the environment (twelve-factor style)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from carecompanion.domain.errors import ConfigError

PROJECT_ROOT = Path(os.environ.get("CARECOMPANION_HOME", Path(__file__).resolve().parents[2]))


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    # Azure / Foundry (required only for commands that call the cloud)
    project_endpoint: str = ""
    resource_endpoint: str = ""
    model_deployment: str = ""
    policy_agent_name: str = "elmfield-policy-agent"

    # Optional integrations
    appointments_api_url: str = ""
    appointments_api_key: str = ""
    scheduling_mcp_url: str = ""
    app_insights_connection_string: str = ""
    audit_log_content: bool = False

    # Paths
    project_root: Path = PROJECT_ROOT

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def state_dir(self) -> Path:
        return self.project_root / "var"

    @property
    def prompts_dir(self) -> Path:
        return self.project_root / "prompts"

    @property
    def hospital_profile_path(self) -> Path:
        return self.project_root / "config" / "hospital.toml"

    @property
    def policies_dir(self) -> Path:
        return self.data_dir / "policies"

    @property
    def safety_fixtures_dir(self) -> Path:
        return self.data_dir / "safety_tests"

    @property
    def discharge_dir(self) -> Path:
        return self.data_dir / "discharge"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            project_endpoint=env.get("FOUNDRY_PROJECT_ENDPOINT", "").strip(),
            resource_endpoint=env.get("FOUNDRY_RESOURCE_ENDPOINT", "").strip(),
            model_deployment=env.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "").strip(),
            policy_agent_name=env.get("POLICY_AGENT_NAME", "elmfield-policy-agent").strip(),
            appointments_api_url=env.get("APPOINTMENTS_API_URL", "").strip().rstrip("/"),
            appointments_api_key=env.get("APPOINTMENTS_API_KEY", "").strip(),
            scheduling_mcp_url=env.get("SCHEDULING_MCP_URL", "").strip(),
            app_insights_connection_string=env.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip(),
            audit_log_content=_flag(env.get("AUDIT_LOG_CONTENT")),
            project_root=Path(env.get("CARECOMPANION_HOME", PROJECT_ROOT)),
        )

    def require_foundry(self, *, need_resource_endpoint: bool = False) -> None:
        """Fail fast, with every problem listed at once, before any cloud call."""
        missing = []
        if not self.project_endpoint:
            missing.append("FOUNDRY_PROJECT_ENDPOINT")
        if not self.model_deployment:
            missing.append("FOUNDRY_MODEL_DEPLOYMENT_NAME")
        if need_resource_endpoint and not self.resource_endpoint:
            missing.append("FOUNDRY_RESOURCE_ENDPOINT")
        if missing:
            raise ConfigError(
                "Missing environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )
