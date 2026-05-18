import os
import logging
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Add the app directory to sys.path if running from within the package
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from agent.bg001_step_3.code.step_3_agent import Step3Agent

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("step-3-launcher")

def main():
    # Load .env file explicitly from the project root
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env"))
    load_dotenv(env_path)

    # Sheet ID from env (same spreadsheet as Step 1)
    spreadsheet_id = os.environ.get("BG001_SHEET_ID", "1erIY6nUrWBzPimCmnvZk6IAFg-mBOwykB9nW8juTDto")

    if not os.environ.get("GOOGLE_CREDENTIALS_BASE64"):
        logger.error("❌ GOOGLE_CREDENTIALS_BASE64 is not set in .env")
        return

    if not os.environ.get("WP_PUBLISH_URL"):
        logger.warning("⚠️ WP_PUBLISH_URL is not set. WordPress publishing will fail.")

    try:
        agent = Step3Agent(spreadsheet_id)
        agent.run()
    except Exception as e:
        logger.error(f"💥 Fatal error during Step 3 agent execution: {e}")

if __name__ == "__main__":
    main()
