"""DEPRECATED SHIM — re-exports ``RuntimeCopilotOrchestrator``.

The canonical orchestrator lives in
``backend.services.ai.runtime_copilot_orchestrator``.

This module exists only to preserve historical import paths. New code
should import from the canonical module. Scheduled for removal in
Phase B3 once all references are migrated.
"""

from backend.services.ai.runtime_copilot_orchestrator import RuntimeCopilotOrchestrator

__all__ = ["RuntimeCopilotOrchestrator"]
