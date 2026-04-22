import logging
from .sheet_service_step1 import SheetServiceStep1
from .rss_service import parse_rss_feed
from .ai_filter import check_packaging_relevance

logger = logging.getLogger(__name__)

class Step1Agent:
    """
    BG001-Phosur-Step -1 Orchestrator.
    Monitors RSS feeds and identifies packaging-related content.
    """
    
    def __init__(self, spreadsheet_id: str):
        self.sheet_service = SheetServiceStep1(spreadsheet_id)
        self.spreadsheet_id = spreadsheet_id

    def run(self):
        """Executes the full agent cycle."""
        logger.info("🚀 Starting BG001 Step -1 Agent...")
        
        # 1. Fetch feeds that are due for processing
        due_feeds = self.sheet_service.get_due_rss_feeds()
        
        if not due_feeds:
            logger.info("🛌 No feeds due for processing. Sleeping.")
            return

        for feed_row in due_feeds:
            rss_url = feed_row.get("rss") or feed_row.get("url")
            row_num = feed_row.get("row_number")
            
            if not rss_url:
                logger.warning(f"⚠️ Row {row_num} has no RSS URL. Skipping.")
                continue

            logger.info(f"🔄 Processing feed: {rss_url} (Row {row_num})")

            # 2. Update next run date immediately (10 days ahead)
            self.sheet_service.update_next_run_date(row_num)

            # 3. Parse RSS Feed
            entries = parse_rss_feed(rss_url)
            
            # 4. Filter entries with AI and save to tracking sheet
            found_count = 0
            for entry in entries:
                relevant_link = check_packaging_relevance(entry)
                
                if relevant_link:
                    self.sheet_service.add_to_tracking_sheet(relevant_link)
                    found_count += 1
            
            logger.info(f"✨ Finished processing {rss_url}. Total relevant items added: {found_count}")

        logger.info("✅ BG001 Step -1 Agent run complete.")
