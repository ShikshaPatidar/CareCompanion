"""Read a PDF with Azure AI Content Understanding (as in lab 5)."""

from __future__ import annotations

from pathlib import Path

from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.identity import DefaultAzureCredential

from carecompanion.domain.errors import ExtractionError


def extract_markdown(resource_endpoint: str, pdf_path: Path, out_path: Path | None = None) -> str:
    """Analyse a PDF and return its content as Markdown (also saved next to it by default).

    resource_endpoint is the Foundry *resource* root, not the project endpoint.
    """
    if not pdf_path.exists():
        raise ExtractionError(f"PDF not found: {pdf_path}")
    client = ContentUnderstandingClient(endpoint=resource_endpoint, credential=DefaultAzureCredential())
    poller = client.begin_analyze_binary(
        analyzer_id="prebuilt-documentSearch",
        binary_input=pdf_path.read_bytes(),
    )
    result = poller.result()
    if not result.contents:
        raise ExtractionError("Content Understanding returned no content")
    markdown = result.contents[0].markdown or ""
    if not markdown.strip():
        raise ExtractionError("Content Understanding returned empty Markdown")
    target = out_path or pdf_path.with_suffix(".md")
    target.write_text(markdown, encoding="utf-8")
    return markdown
