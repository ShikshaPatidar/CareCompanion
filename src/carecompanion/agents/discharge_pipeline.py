"""Sequential workflow: discharge note -> facts -> patient-friendly summary (as in lab 6)."""

from __future__ import annotations

from agent_framework import Agent
from agent_framework.orchestrations import SequentialBuilder

from carecompanion.agents.factory import AzureClients
from carecompanion.agents.prompts import PromptLibrary


async def summarise_discharge_note(clients: AzureClients, prompts: PromptLibrary, note_markdown: str) -> str:
    extractor = Agent(
        client=clients.chat_client(),
        name="NoteExtractor",
        instructions=prompts.render("discharge_extractor"),
    )
    writer = Agent(
        client=clients.chat_client(),
        name="PatientWriter",
        instructions=prompts.render("discharge_writer"),
    )
    workflow = SequentialBuilder(participants=[extractor, writer]).build()
    result = await workflow.run("Create the after-visit summary for this note:\n\n" + note_markdown)
    outputs = [str(o) for o in result.get_outputs()]
    return "\n".join(outputs).strip()
