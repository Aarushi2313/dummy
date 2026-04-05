from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Dict, Hashable, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from langgraph.graph import END, START, StateGraph

from schemas import DocumentMetadata, FinalReportJSON, NormalizedIntent, ValidationError
from services.db_service import DatabaseService
from services.gemini_service import GeminiReportingService


class FeedbackAction(str, Enum):
    NONE = "none"
    APPLY_CORRECTION = "apply_correction"
    CONSOLIDATE = "consolidate"


class AgentDocumentInput(BaseModel):
    file_base64: Optional[str] = Field(default=None, alias="fileBase64")
    file_name: Optional[str] = Field(default=None, alias="fileName")
    file_size: Optional[int] = Field(default=None, alias="fileSize")
    mime_type: Optional[str] = Field(default=None, alias="mimeType")  # computed from file_name if missing
    model_config = ConfigDict(populate_by_name=True)


class AgentState(BaseModel):
    # Inputs
    prompt: Optional[str] = None
    document: AgentDocumentInput = Field(default_factory=AgentDocumentInput)

    # Derived artifacts
    intent: Optional[NormalizedIntent] = None
    report: Optional[FinalReportJSON] = None

    # Memory (long-term style rules stored in Supabase)
    memory: str = "Apply standard professional reporting standards."

    # Feedback evolution (short-term refinement vs long-term consolidation)
    feedback_action: FeedbackAction = FeedbackAction.NONE
    next_suggestion: Optional[str] = None
    feedback_history: List[str] = Field(default_factory=list)
    feedback_score: float = 1.0  # used when persisting audit logs during consolidation

    # Pending consolidation artifacts (produced by feedback_processing, applied in memory_update)
    pending_new_memory: Optional[str] = None
    pending_interaction_summary: Optional[str] = None

    # Guardrail routing
    low_signal: Optional[bool] = None
    status: Literal[
        "in_progress",
        "needs_clarification",
        "rejected_low_signal",
        "completed",
        "error",
    ] = "in_progress"
    clarification_question: Optional[str] = None
    rejection_reason: Optional[str] = None
    error: Optional[ValidationError] = None

    # Idempotency helpers (avoid duplicated DB writes on retries)
    initial_intent_stored: bool = False


class AgentDeps:
    def __init__(self, gemini: GeminiReportingService, db: DatabaseService):
        self.gemini = gemini
        self.db = db


def _build_doc_metadata(doc: AgentDocumentInput) -> DocumentMetadata:
    """
    Mirror existing logic from the React client:
    - PDF => pdf
    - TXT/DOCX/others => txt fallback (backend schema only constrains values)
    """
    attached = bool(doc.file_base64)
    file_name = doc.file_name
    file_type = "none"
    if file_name:
        lower = file_name.lower()
        if lower.endswith(".pdf"):
            file_type = "pdf"
        elif lower.endswith(".docx"):
            file_type = "docx"
        elif lower.endswith(".txt"):
            file_type = "txt"
        else:
            file_type = "txt"
    elif attached:
        file_type = "txt"

    return DocumentMetadata(
        attached=attached,
        file_type=file_type,
        file_name=file_name,
        content=None,
        size=doc.file_size,
        low_signal=None,
    )


def _infer_mime_type(doc: AgentDocumentInput, doc_meta: DocumentMetadata) -> str:
    if doc.mime_type:
        return doc.mime_type
    return "application/pdf" if doc_meta.file_type == "pdf" else "text/plain"


def _route_after_ambiguity(state: AgentState) -> Hashable:
    if state.status == "error":
        return "error_node"
    if state.intent is None:
        return "error_node"
    if state.intent.is_ambiguous:
        return "clarification_node"
    return "signal_check"


def _route_after_signal_check(state: AgentState) -> Hashable:
    if state.status == "error":
        return "error_node"
    if state.low_signal is False:
        # Signal OK
        return "memory_fetch"
    if state.low_signal is True:
        return "rejection_node"

    # If not evaluated yet, default to signal_fetch path for correctness.
    # This should not happen in normal flows because `signal_check` always runs.
    return "memory_fetch"


async def intent_normalization_node(state: AgentState, deps: AgentDeps) -> Dict[str, Any]:
    # Run normalization on:
    # - initial call (intent missing)
    # - explicit ambiguity retry (status == needs_clarification)
    # - explicit low-signal restart (status == rejected_low_signal)
    # - errors should be re-attempted only if caller resets them (status != error)
    if state.status not in ("needs_clarification", "rejected_low_signal") and state.intent is not None:
        # Keep existing intent when we're continuing refinement/consolidation.
        return {}

    if (not state.prompt or not state.prompt.strip()) and not state.document.file_base64:
        err = ValidationError(
            error_type="INVALID_PROMPT",
            message="Guardrail: Please provide a prompt or a document to analyze.",
        )
        return {
            "status": "error",
            "error": err,
        }

    if not state.prompt or not state.prompt.strip():
        # Geminis normalize_intent expects prompt string; in your UI you always provide prompt.
        err = ValidationError(
            error_type="INVALID_PROMPT",
            message="Guardrail: Missing prompt text.",
        )
        return {"status": "error", "error": err}

    doc_meta = _build_doc_metadata(state.document)

    try:
        intent = await deps.gemini.normalize_intent(state.prompt, doc_meta)
    except Exception as e:
        # normalize_intent throws for unsupported tasks (see gemini_service)
        message = str(e)
        err_type = "IRRELEVANT" if "IRRELEVANT" in message else "UNSUPPORTED_TASK"
        err = ValidationError(error_type=err_type, message=message)
        return {"status": "error", "error": err}

    # Clear per-run guardrail outputs; downstream nodes decide next routing.
    return {
        "intent": intent,
        "status": "in_progress",
        "clarification_question": None,
        "rejection_reason": None,
        "error": None,
        "low_signal": None,
    }


def ambiguity_check_node(state: AgentState) -> Dict[str, Any]:
    # This node intentionally does not call Gemini.
    # Guardrail routing is done via conditional edges based on intent.is_ambiguous.
    if state.status == "error":
        return {}
    if state.intent is None:
        err = ValidationError(error_type="AMBIGUOUS", message="Intent missing before ambiguity check.")
        return {"status": "error", "error": err}
    return {}


async def clarification_node(state: AgentState) -> Dict[str, Any]:
    question = (
        "Synthesis confidence is below 40%. Please clarify your specific analytical objective to ensure grounding accuracy."
    )
    if state.intent and state.intent.content_scope:
        question += f"\nSuggested scope: {state.intent.content_scope}"
    return {
        "status": "needs_clarification",
        "clarification_question": question,
        "rejection_reason": None,
        "error": None,
    }


async def signal_check_node(state: AgentState, deps: AgentDeps) -> Dict[str, Any]:
    if state.status == "error":
        return {}

    # Refinement/consolidation should not re-run resource signal validation.
    # Your current frontend calls `/refine-report` without reapplying guardrails.
    if state.feedback_action != FeedbackAction.NONE and state.report is not None:
        return {"low_signal": False, "status": "in_progress", "rejection_reason": None}

    # If no document, treat as signal OK.
    if not state.document.file_base64:
        return {"low_signal": False}

    if state.intent is None:
        err = ValidationError(error_type="LOW_SIGNAL", message="Intent missing before signal check.")
        return {"status": "error", "error": err}

    doc_meta = _build_doc_metadata(state.document)
    mime_type = _infer_mime_type(state.document, doc_meta)

    try:
        has_signal = await deps.gemini.check_document_signal(state.document.file_base64, mime_type)
    except Exception:
        # Preserve existing behavior: if signal check fails, allow progression.
        has_signal = True

    if not has_signal:
        return {
            "low_signal": True,
            "status": "rejected_low_signal",
            "rejection_reason": "Low Signal Detected: Provided asset lacks sufficient analytical signal.",
        }

    return {"low_signal": False, "status": "in_progress", "rejection_reason": None}


async def rejection_node(state: AgentState) -> Dict[str, Any]:
    reason = state.rejection_reason or "Low Signal Detected: Resource Guardrail triggered."
    return {
        "status": "rejected_low_signal",
        "rejection_reason": reason,
        "clarification_question": None,
        "error": None,
    }


async def memory_fetch_node(state: AgentState, deps: AgentDeps) -> Dict[str, Any]:
    if state.status in ("needs_clarification", "rejected_low_signal", "error"):
        return {}

    # If we're already refining or consolidating, keep the active session memory.
    if state.feedback_action != FeedbackAction.NONE and state.report is not None:
        return {}

    if state.intent is None:
        err = ValidationError(error_type="LOW_SIGNAL", message="Intent missing before memory_fetch.")
        return {"status": "error", "error": err}

    memory = await deps.db.get_preferences(state.intent.detected_category)
    return {"memory": memory}


async def report_generation_node(state: AgentState, deps: AgentDeps) -> Dict[str, Any]:
    if state.status in ("needs_clarification", "rejected_low_signal", "error"):
        return {}

    # Refinement/consolidation should operate on the existing report.
    # This mirrors the current UI behavior (refine without regenerating from scratch).
    if state.feedback_action != FeedbackAction.NONE and state.report is not None:
        return {}

    if state.intent is None:
        err = ValidationError(error_type="INVALID_PROMPT", message="Intent missing before report_generation.")
        return {"status": "error", "error": err}

    try:
        if not state.initial_intent_stored:
            # Mirrors your current UI: store request once, before generate-report.
            await deps.db.store_initial_intent(state.intent)
    except Exception:
        # DB failures should not block report generation.
        pass

    file_base64 = state.document.file_base64
    try:
        report = await deps.gemini.generate_report(
            intent=state.intent,
            file_base64=file_base64,
            memory_context=state.memory,
        )
    except Exception as e:
        err = ValidationError(
            error_type="UNSUPPORTED_TASK",
            message=str(e),
        )
        return {"status": "error", "error": err}

    return {
        "report": report,
        "initial_intent_stored": True,
        "status": "completed",
    }


async def feedback_processing_node(state: AgentState, deps: AgentDeps) -> Dict[str, Any]:
    if state.status in ("needs_clarification", "rejected_low_signal", "error"):
        return {}

    if state.feedback_action == FeedbackAction.NONE:
        return {}

    if state.intent is None or state.report is None:
        err = ValidationError(error_type="INVALID_FORMAT", message="Missing intent/report before feedback_processing.")
        return {"status": "error", "error": err}

    # APPLY_CORRECTION: refine an existing report
    if state.feedback_action == FeedbackAction.APPLY_CORRECTION:
        if not state.next_suggestion or not state.next_suggestion.strip():
            err = ValidationError(error_type="INVALID_FORMAT", message="Missing suggestion for apply_correction.")
            return {"status": "error", "error": err}

        try:
            refined = await deps.gemini.refine_report(
                previous_report=state.report,
                suggestion=state.next_suggestion,
                intent=state.intent,
                memory_context=state.memory,
            )
        except Exception as e:
            err = ValidationError(error_type="UNSUPPORTED_TASK", message=str(e))
            return {"status": "error", "error": err}

        new_hist = list(state.feedback_history)
        new_hist.append(state.next_suggestion)

        return {
            "report": refined,
            "feedback_history": new_hist,
            "next_suggestion": None,
            "feedback_action": FeedbackAction.NONE,
            "status": "completed",
        }

    # CONSOLIDATE: learn durable style rules from feedback history
    if state.feedback_action == FeedbackAction.CONSOLIDATE:
        try:
            extracted = await deps.gemini.extract_style_preferences(
                intent=state.intent,
                iterations=list(state.feedback_history),
                final_report=state.report,
                current_memory=state.memory,
            )
        except Exception as e:
            err = ValidationError(error_type="UNSUPPORTED_TASK", message=str(e))
            return {"status": "error", "error": err}

        return {
            "pending_new_memory": extracted.get("newMemory") or state.memory,
            "pending_interaction_summary": extracted.get("interactionSummary") or "Session complete.",
            "status": "completed",
        }

    return {}


async def memory_update_node(state: AgentState, deps: AgentDeps) -> Dict[str, Any]:
    if state.status in ("needs_clarification", "rejected_low_signal", "error"):
        return {}

    if state.feedback_action != FeedbackAction.CONSOLIDATE:
        return {}

    if state.intent is None:
        err = ValidationError(error_type="INVALID_FORMAT", message="Intent missing before memory_update.")
        return {"status": "error", "error": err}

    if not state.pending_new_memory:
        err = ValidationError(error_type="INVALID_FORMAT", message="No pending_new_memory available for memory_update.")
        return {"status": "error", "error": err}

    try:
        await deps.db.update_preference(state.intent.detected_category, state.pending_new_memory)
    except Exception as e:
        # Memory update failure should not corrupt the report, but should be visible.
        err = ValidationError(error_type="UNSUPPORTED_TASK", message=f"Memory consolidation failed: {e}")
        return {"status": "error", "error": err}

    try:
        await deps.db.store_interaction_summary(
            request_id=state.intent.request_id,
            category=state.intent.detected_category,
            summary=state.pending_interaction_summary or "Session complete.",
            score=float(state.feedback_score),
        )
    except Exception:
        # Audit failures should not block the update.
        pass

    return {
        "memory": state.pending_new_memory,
        "pending_new_memory": None,
        "pending_interaction_summary": None,
        "feedback_history": [],
        "feedback_action": FeedbackAction.NONE,
    }


def build_agent_graph(*, deps: AgentDeps) -> StateGraph:
    builder: StateGraph = StateGraph(AgentState)

    # Core pipeline nodes
    async def intent_normalization(state: AgentState) -> Dict[str, Any]:
        return await intent_normalization_node(state, deps)

    def ambiguity_check(state: AgentState) -> Dict[str, Any]:
        return ambiguity_check_node(state)

    async def clarification(state: AgentState) -> Dict[str, Any]:
        return await clarification_node(state)

    async def signal_check(state: AgentState) -> Dict[str, Any]:
        return await signal_check_node(state, deps)

    async def rejection(state: AgentState) -> Dict[str, Any]:
        return await rejection_node(state)

    async def memory_fetch(state: AgentState) -> Dict[str, Any]:
        return await memory_fetch_node(state, deps)

    async def report_generation(state: AgentState) -> Dict[str, Any]:
        return await report_generation_node(state, deps)

    async def feedback_processing(state: AgentState) -> Dict[str, Any]:
        return await feedback_processing_node(state, deps)

    async def memory_update(state: AgentState) -> Dict[str, Any]:
        return await memory_update_node(state, deps)

    def error_node(state: AgentState) -> Dict[str, Any]:
        # Error state is already stored by upstream nodes.
        return {"status": "error"}

    builder.add_node("intent_normalization", intent_normalization)
    builder.add_node("ambiguity_check", ambiguity_check)
    builder.add_node("clarification_node", clarification)
    builder.add_node("signal_check", signal_check)
    builder.add_node("rejection_node", rejection)
    builder.add_node("memory_fetch", memory_fetch)
    builder.add_node("report_generation", report_generation)
    builder.add_node("feedback_processing", feedback_processing)
    builder.add_node("memory_update", memory_update)
    builder.add_node("error_node", error_node)

    builder.add_edge(START, "intent_normalization")
    builder.add_edge("intent_normalization", "ambiguity_check")

    builder.add_conditional_edges(
        "ambiguity_check",
        _route_after_ambiguity,
        {
            "clarification_node": "clarification_node",
            "signal_check": "signal_check",
            "error_node": "error_node",
        },
    )

    builder.add_edge("clarification_node", END)
    builder.add_edge("rejection_node", END)
    builder.add_edge("error_node", END)

    builder.add_conditional_edges(
        "signal_check",
        _route_after_signal_check,
        {
            "memory_fetch": "memory_fetch",
            "rejection_node": "rejection_node",
            "error_node": "error_node",
        },
    )

    builder.add_edge("memory_fetch", "report_generation")
    builder.add_edge("report_generation", "feedback_processing")
    builder.add_edge("feedback_processing", "memory_update")
    builder.add_edge("memory_update", END)

    return builder


def compile_agent_graph(*, builder: StateGraph, checkpointer: Any) -> Any:
    """
    Caller-owned checkpointer so they can manage lifecycle (startup/shutdown) in FastAPI.
    """
    return builder.compile(checkpointer=checkpointer)

