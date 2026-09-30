"""Optional tracing. Without configuration everything here is a harmless no-op."""

from __future__ import annotations

import logging

from opentelemetry import trace

from carecompanion.config import Settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("carecompanion")


def setup_telemetry(settings: Settings) -> bool:
    """Send traces to Application Insights when a connection string is configured.

    Returns True when exporting is enabled. The Agent Framework already emits spans for
    agent and tool calls; our own spans (guardrails, tools) join the same trace.
    """
    if not settings.app_insights_connection_string:
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logger.warning(
            "APPLICATIONINSIGHTS_CONNECTION_STRING is set but azure-monitor-opentelemetry is "
            'not installed. Run: pip install -e ".[telemetry]"'
        )
        return False
    configure_azure_monitor(connection_string=settings.app_insights_connection_string)
    logger.info("Tracing enabled (Application Insights)")
    return True
