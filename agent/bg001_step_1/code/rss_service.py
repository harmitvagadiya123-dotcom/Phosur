import feedparser
import logging
from typing import List, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def parse_rss_feed(url: str) -> List[Dict]:
    """
    Fetches and parses an RSS feed from the given URL.
    Returns a list of dicts with title, link, and summary.
    """
    try:
        logger.info(f"📡 Fetching RSS feed: {url}")
        feed = feedparser.parse(url)
        
        if feed.bozo:
            logger.warning(f"⚠️ RSS feed parsing warning (Bozo): {feed.bozo_exception}")

        entries = []
        for entry in feed.entries:
            # Clean summary from HTML tags
            summary_html = entry.get("summary", "") or entry.get("description", "")
            summary_clean = BeautifulSoup(summary_html, "html.parser").get_text() if summary_html else ""
            
            entries.append({
                "title": entry.get("title", "No Title"),
                "link": entry.get("link", ""),
                "summary": summary_clean[:500],  # Limit summary size for AI processing
                "published": entry.get("published", "")
            })
            
        logger.info(f"✅ Found {len(entries)} entries in feed.")
        return entries

    except Exception as e:
        logger.error(f"❌ Failed to parse RSS feed from {url}: {e}")
        return []
