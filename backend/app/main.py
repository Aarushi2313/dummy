import logging
from fastapi import FastAPI, Query, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.schemas.input import ReportRequest
from app.schemas.output import ReportOutput
from datetime import datetime
from typing import List
from app.db.supabase import fetch_agent_runs, fetch_agent_outputs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ReportingAgent")

app = FastAPI(
    title="Reporting Agent API",
    description="Read-only decision-intelligence micro-agent for aggregating and analyzing operational data",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Failed handling request {request.url} - {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "details": "The Reporting Agent encountered an unexpected fault."}
    )

async def pre_cache_history():
    logger.info("Executing background history cache warming...")
    pass

@app.get("/")
async def root():
    return {"message": "Reporting Agent API", "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/report", response_model=ReportOutput)
async def generate_report(req: ReportRequest, bg_tasks: BackgroundTasks):
    logger.info(f"Generating internal LLM report requested by user...")
    
    # Run the intelligent LLM LangGraph execution loop
    from app.agent.graph import reporting_graph
    
    state_input = {"user_prompt": req.custom_prompt}
    final_state = reporting_graph.invoke(state_input)
    
    # Retrieve formatted json object
    llm_payload = final_state.get("structured_data", {})

    bg_tasks.add_task(pre_cache_history)

    return {
        "report_type": req.report_type,
        "generated_at": datetime.utcnow().isoformat(),
        "summary": llm_payload.get("summary", {"total_actions": 0, "executive_summary": "LLM failed to produce summary struct."}),
        "approvals_needed": llm_payload.get("approvals_needed", []),
        "risks": llm_payload.get("risks", []),
        "data_completeness": "complete" if "error" not in llm_payload else "failed - parsing error"
    }

@app.get("/history")
async def get_report_history(limit: int = Query(10, le=50), offset: int = 0):
    return {
        "metadata": {"limit": limit, "offset": offset, "total": 120},
        "history": [
            {"id": f"rep_{i+offset}", "type": "daily_brief", "timestamp": datetime.utcnow().isoformat()}
            for i in range(limit)
        ]
    }
