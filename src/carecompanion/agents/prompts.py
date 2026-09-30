"""Prompts are versioned files in prompts/, with hospital facts injected from config."""

from __future__ import annotations

from pathlib import Path
from string import Template

from carecompanion.domain.errors import ConfigError


class PromptLibrary:
    def __init__(self, prompts_dir: Path, variables: dict[str, str]) -> None:
        self._dir = prompts_dir
        self._variables = variables

    def render(self, name: str) -> str:
        path = self._dir / f"{name}.md"
        try:
            template = Template(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"Cannot read prompt {path}: {exc}") from exc
        try:
            return template.substitute(self._variables).strip()
        except KeyError as exc:
            raise ConfigError(f"Prompt {path.name} uses undefined variable {exc}") from exc
        except ValueError as exc:
            raise ConfigError(f"Prompt {path.name} has a malformed placeholder: {exc}") from exc

    def raw(self, name: str) -> str:
        """Prompt text with no substitution, for templates that are completed later."""
        return (self._dir / f"{name}.md").read_text(encoding="utf-8")
