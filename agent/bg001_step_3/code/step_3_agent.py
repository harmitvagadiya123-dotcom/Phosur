import logging
from .sheet_service_step3 import SheetServiceStep3
from .slug_service import generate_slug
from .wp_publisher import publish_to_wordpress

logger = logging.getLogger(__name__)


class Step3Agent:
    """
    BG001-Phosur Step 3 Orchestrator.

    Workflow (mirrors the n8n pipeline):
      1. Read the first approved row from Gumloop_Blog_Creation
         (status=complete AND publish status=Approved)
      2. Validate title and feature image are present
         → If missing: mark row as Errored
      3. Generate a URL slug from the title
      4. POST to WordPress endpoint
      5. On success: mark row as Published
    """

    def __init__(self, spreadsheet_id: str):
        self.sheet_service = SheetServiceStep3(spreadsheet_id)
        self.spreadsheet_id = spreadsheet_id

    def run(self):
        """Executes the full Step 3 agent cycle."""
        logger.info("🚀 Starting BG001 Step 3 Agent...")

        # 1. Get first approved row
        row = self.sheet_service.get_approved_row()

        if not row:
            logger.info("🛌 No approved rows found for publishing. Nothing to do.")
            return

        row_number = row.get("row_number")
        title = str(row.get("title", "")).strip()
        feature_image = str(row.get("feature image", "")).strip()
        html_content = str(row.get("html", "")).strip()
        url = str(row.get("url", "")).strip()

        logger.info(f"📋 Found approved row {row_number}: title='{title[:50]}...', url='{url}'")

        # 2. Validate: title and feature image must not be empty
        if not title or not feature_image:
            logger.warning(
                f"⚠️ Row {row_number} failed validation — "
                f"title empty: {not title}, feature image empty: {not feature_image}"
            )
            self.sheet_service.update_row_errored(row_number)
            return

        # 3. Generate slug from title
        slug = generate_slug(title)

        # 4. Publish to WordPress
        wp_response = publish_to_wordpress(
            slug=slug,
            title=title,
            html_content=html_content,
            featured_image_url=feature_image,
        )

        if wp_response:
            # 5. Success → update sheet as Published
            data = wp_response.get("data", {})
            if isinstance(data, dict):
                wp_title = data.get("title", title)
                wp_slug = data.get("slug", slug)
            else:
                wp_title = title
                wp_slug = slug
            self.sheet_service.update_row_published(row_number, wp_title, wp_slug)
            logger.info(f"✅ BG001 Step 3 complete — published: {wp_slug}")
        else:
            logger.error(f"❌ WordPress publish failed for row {row_number}. Row NOT updated.")

        logger.info("✅ BG001 Step 3 Agent run complete.")
