"""
Buying Intent LinkedIn Agent — FastAPI Webhook Server

Replaces the n8n workflow for Phosur's LinkedIn buying intent pipeline.
Receives webhook POSTs from Google Apps Script, processes leads via the
BuyingIntentAgent, and returns status to the script.

Endpoints:
  GET  /health                  → Health check (for Render/AWS)
  POST /webhook/buying-intent   → Process a high-intent lead
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.buying_intent.code.buying_intent_agent import BuyingIntentAgent

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("buying-intent-server")


# ── App Lifecycle ────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("🚀 Buying Intent LinkedIn Agent — STARTED")
    logger.info(f"   NOTIFY_TO : {os.environ.get('NOTIFY_TO', 'not set')}")
    logger.info(f"   NOTIFY_CC : {os.environ.get('NOTIFY_CC', 'not set')}")
    logger.info(f"   SHEET_ID  : {os.environ.get('GOOGLE_SHEET_ID', 'default')}")
    logger.info("=" * 60)
    yield
    logger.info("🛑 Buying Intent LinkedIn Agent — STOPPED")


# ── FastAPI App ──────────────────────────────────────────
app = FastAPI(
    title="Buying Intent LinkedIn Agent",
    description="Replaces n8n webhook → email → sheet update pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# Singleton agent instance
agent = BuyingIntentAgent()


# ── Root Endpoint ──────────────────────────────────────────
@app.get("/")
async def root():
    """Service landing page for quick deployment checks."""
    return {
        "status": "online",
        "service": "Buying Intent Agent",
        "webhook_url": "/webhook/buying-intent"
    }


# ── Health Check ─────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check endpoint for Render / AWS."""
    return {"status": "healthy", "agent": "buying-intent-linkedin", "version": "1.0.1"}


# ── Webhook Diagnostic Handler ───────────────────────────
@app.get("/webhook/buying-intent")
async def webhook_diagnostic():
    """Helpful message for accidental GET requests to the webhook URL."""
    return {
        "error": "Method Not Allowed",
        "message": "This endpoint requires a POST request from Google Apps Script. "
                   "If you are seeing this in a browser, the endpoint is working correctly."
    }


# ── Webhook Endpoint ─────────────────────────────────────
@app.post("/webhook/buying-intent")
async def webhook_buying_intent(request: Request):
    """
    Receive a high-intent lead from Google Apps Script.

    Expected JSON payload:
    {
        "row_number": 2,
        "SNO": 1,
        "DATE": "2026-04-20",
        "NAME": "John Doe",
        "COUNTRY": "India",
        "DESIGNATIONORCOMPANY": "Acme Corp",
        "LINKEDIN": "https://linkedin.com/in/johndoe",
        "ConversationHistory": "...",
        "BuyingIntent": "High"
    }
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"❌ Invalid JSON in request: {e}")
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid JSON payload"},
        )

    logger.info(f"📨 Webhook received: {payload.get('NAME', 'Unknown')} (Row {payload.get('row_number', '?')})")

    # Process through the agent
    result = agent.process(payload)

    # Log specific failure reasons if 207 (partial success)
    if not result.success:
        logger.warning(f"⚠️ Partial Success (207) for '{payload.get('NAME')}':")
        logger.warning(f"   Message : {result.message}")
        if result.error:
            logger.warning(f"   Error   : {result.error}")

    status_code = 200 if result.success else 207  # 207 = partial success

    return JSONResponse(
        status_code=status_code,
        content={
            "success": result.success,
            "email_sent": result.email_sent,
            "sheet_updated": result.sheet_updated,
            "message": result.message,
            "error": result.error,
        },
    )


# ── BG001 Step 1 Endpoint ──────────────────────────────────
from agent.bg001_step_1.code.step_1_agent import Step1Agent
from fastapi import BackgroundTasks

def run_bg001_agent_task():
    spreadsheet_id = os.environ.get("BG001_SHEET_ID", "1bnz46ES2olQP7vPqvIpthBhF08TQ5RCN28ytcjjszsM")
    try:
        agent_step1 = Step1Agent(spreadsheet_id)
        agent_step1.run()
    except Exception as e:
        import traceback
        logger.error(f"💥 Fatal error during bg001 agent execution: {e}\n{traceback.format_exc()}")

@app.post("/webhook/run-bg001")
async def webhook_run_bg001(background_tasks: BackgroundTasks):
    """
    Trigger the BG001 Step 1 Agent to run in the background.
    Useful for external cron services (like cron-job.org or Google Apps Script).
    """
    background_tasks.add_task(run_bg001_agent_task)
    return {"status": "success", "message": "BG001 Step 1 Agent started in the background."}

# ── Run with Uvicorn ─────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
