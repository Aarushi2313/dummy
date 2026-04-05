import os
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from services.gemini_service import GeminiReportingService
from services.db_service import DatabaseService
from schemas import FinalReportJSON, NormalizedIntent, DocumentMetadata
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from langgraph_agent import (
    AgentDeps,
    AgentDocumentInput,
    AgentState,
    FeedbackAction,
    build_agent_graph,
    compile_agent_graph,
)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

gemini_service = GeminiReportingService()
db_service = DatabaseService()

async def _init_langgraph() -> None:
    """
    Initialize LangGraph once per process and keep the checkpoint saver open
    for the app lifetime.
    """
    deps = AgentDeps(gemini=gemini_service, db=db_service)
    builder = build_agent_graph(deps=deps)

    checkpoint_path = os.getenv("LANGGRAPH_CHECKPOINT_PATH", "backend_checkpoints.sqlite")
    cm = AsyncSqliteSaver.from_conn_string(checkpoint_path)
    checkpointer = await cm.__aenter__()
    app.state._langgraph_checkpointer_cm = cm
    app.state._langgraph_checkpointer = checkpointer
    app.state._langgraph_graph = compile_agent_graph(builder=builder, checkpointer=checkpointer)


async def _shutdown_langgraph() -> None:
    cm = getattr(app.state, "_langgraph_checkpointer_cm", None)
    if cm is not None:
        await cm.__aexit__(None, None, None)


@app.on_event("startup")
async def on_startup():
    try:
        await _init_langgraph()
    except Exception as e:
        # Keep app bootable even if checkpointing fails.
        # Endpoints will raise when called.
        app.state._langgraph_init_error = str(e)


@app.on_event("shutdown")
async def on_shutdown():
    await _shutdown_langgraph()


class NormalizeIntentRequest(BaseModel):
    prompt: str
    docMeta: DocumentMetadata

class CheckSignalRequest(BaseModel):
    fileBase64: str
    mimeType: str

class GenerateReportRequest(BaseModel):
    intent: NormalizedIntent
    fileBase64: Optional[str] = None
    memoryContext: str = ""

class RefineReportRequest(BaseModel):
    previousReport: FinalReportJSON
    suggestion: str
    intent: NormalizedIntent
    memoryContext: str = ""

class ExtractStyleRequest(BaseModel):
    intent: NormalizedIntent
    iterations: List[str]
    finalReport: FinalReportJSON
    currentMemory: str

class StoreInteractionRequest(BaseModel):
    requestId: str
    category: str
    summary: str
    score: float


class AgentRunRequest(BaseModel):
    thread_id: Optional[str] = None
    prompt: Optional[str] = None
    document: Optional[AgentDocumentInput] = None


class AgentFeedbackRequest(BaseModel):
    thread_id: str
    feedback_action: FeedbackAction
    next_suggestion: Optional[str] = None
    feedback_score: Optional[float] = None

@app.post("/store-interaction")
async def store_interaction(request: StoreInteractionRequest):
    await db_service.store_interaction_summary(request.requestId, request.category, request.summary, request.score)
    return {"status": "success"}

@app.post("/agent/run")
async def agent_run(request: AgentRunRequest) -> Dict[str, Any]:
    """
    Starts (or resumes) the LangGraph workflow for guarded reporting.

    - Uses `thread_id` for checkpointed state.
    - Returns `status` + guardrail fields (`clarification_question`, `rejection_reason`)
      or a completed `report` payload.
    """
    graph = getattr(app.state, "_langgraph_graph", None)
    if graph is None:
        raise HTTPException(status_code=500, detail=getattr(app.state, "_langgraph_init_error", "LangGraph not initialized"))

    thread_id = request.thread_id or uuid.uuid4().hex

    update = request.model_dump(exclude_unset=True)
    update.pop("thread_id", None)
    # LangGraph/Pydantic expects `document` to be either omitted or a dict.
    # If the client sends `document: null`, drop it so defaults apply.
    if update.get("document") is None:
        update.pop("document", None)

    # Ensure this run path is not treated as a refinement/consolidation step.
    update["feedback_action"] = FeedbackAction.NONE

    # Use checkpointed state; config key is required for LangGraph persistence.
    try:
        state_dict = await graph.ainvoke(
            update,
            config={"configurable": {"thread_id": thread_id}},
        )
        state = AgentState.model_validate(state_dict)
        return {"thread_id": thread_id, **state.model_dump()}
    except Exception as e:
        return {
            "thread_id": thread_id,
            "status": "error",
            "error": {"status": "error", "error_type": "UNSUPPORTED_TASK", "message": str(e)},
        }


@app.post("/agent/feedback")
async def agent_feedback(request: AgentFeedbackRequest) -> Dict[str, Any]:
    """
    Applies feedback to the checkpointed state:
    - `apply_correction` triggers report refinement
    - `consolidate` triggers durable memory consolidation
    """
    graph = getattr(app.state, "_langgraph_graph", None)
    if graph is None:
        raise HTTPException(status_code=500, detail=getattr(app.state, "_langgraph_init_error", "LangGraph not initialized"))

    thread_id = request.thread_id
    update = request.model_dump(exclude_unset=True)
    update.pop("thread_id", None)

    # Normalize: if consolidating, score defaults to 1.0.
    if request.feedback_action == FeedbackAction.CONSOLIDATE and "feedback_score" not in update:
        update["feedback_score"] = 1.0

    try:
        state_dict = await graph.ainvoke(
            update,
            config={"configurable": {"thread_id": thread_id}},
        )
        state = AgentState.model_validate(state_dict)
        return {"thread_id": thread_id, **state.model_dump()}
    except Exception as e:
        return {
            "thread_id": thread_id,
            "status": "error",
            "error": {"status": "error", "error_type": "UNSUPPORTED_TASK", "message": str(e)},
        }

@app.post("/normalize-intent")
async def normalize_intent(request: NormalizeIntentRequest):
    try:
        intent = await gemini_service.normalize_intent(request.prompt, request.docMeta)
        # Background logging to DB
        await db_service.store_initial_intent(intent)
        return intent
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/check-document-signal")
async def check_document_signal(request: CheckSignalRequest):
    result = await gemini_service.check_document_signal(request.fileBase64, request.mimeType)
    return {"has_signal": result}

@app.post("/generate-report")
async def generate_report(request: GenerateReportRequest):
    try:
        report = await gemini_service.generate_report(request.intent, request.fileBase64, request.memoryContext)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refine-report")
async def refine_report(request: RefineReportRequest):
    try:
        report = await gemini_service.refine_report(request.previousReport, request.suggestion, request.intent, request.memoryContext)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract-style-preferences")
async def extract_style_preferences(request: ExtractStyleRequest):
    try:
        result = await gemini_service.extract_style_preferences(
            request.intent, request.iterations, request.finalReport, request.currentMemory
        )
        # Background update preference
        await db_service.update_preference(request.intent.detected_category, result["newMemory"])
        # Background store interaction
        # Note: score is not passed in request here, so skipping store_interaction_summary for now or need to add to request
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/preferences/{category}")
async def get_preferences(category: str):
    rules = await db_service.get_preferences(category)
    return {"preference_rules": rules}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
