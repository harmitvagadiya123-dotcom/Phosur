"""
html_utils.py — Strip HTML tags from email content.
Replicates the n8n Code node that cleans incoming email bodies.
"""
import re
import logging

logger = logging.getLogger(__name__)


def strip_html(html: str) -> str:
    """
    Remove all HTML tags, scripts, and styles from email content.
    Normalise whitespace. Returns plain text.
    """
    if not html:
        return ""

    # Remove <script> blocks
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    # Remove <style> blocks
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    # Remove all remaining HTML tags
    text = re.sub(r"</?[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # Normalise whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text
