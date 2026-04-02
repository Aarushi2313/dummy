from fastapi import FastAPI

app = FastAPI(
    title="Reporting Agent API",
    description="Read-only decision-intelligence micro-agent for aggregating and analyzing operational data",
    version="1.0.0"
)

@app.get("/")
def root():
    return {
        "message": "Reporting Agent API",
        "status": "running"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}
