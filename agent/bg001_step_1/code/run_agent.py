import os
import logging
from dotenv import load_dotenv

# Add the app directory to sys.path if running from within the package
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from agent.bg001_step_1.code.step_1_agent import Step1Agent

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("step-1-launcher")

def main():
    # Load .env file
    load_dotenv()

    # Sheet ID from the workflow (BG001-Phosur-Scenario)
    # You can also set this in .env as BG001_SHEET_ID
    spreadsheet_id = os.environ.get("BG001_SHEET_ID", "1erIY6nUrWBzPimCmnvZk6IAFg-mBOwykB9nW8juTDto")

    if not os.environ.get("GOOGLE_CREDENTIALS_BASE64"):
        logger.error("❌ GOOGLE_CREDENTIALS_BASE64 is not set in .env")
        return

    if not os.environ.get("OPENROUTER_API_KEY"):
        logger.warning("⚠️ OPENROUTER_API_KEY is not set. AI filtering will fail.")

    try:
        agent = Step1Agent(spreadsheet_id)
        agent.run()
    except Exception as e:
        logger.error(f"💥 Fatal error during agent execution: {e}")

if __name__ == "__main__":
    main()
