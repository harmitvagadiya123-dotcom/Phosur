import re
import logging
import unicodedata

logger = logging.getLogger(__name__)


def generate_slug(text: str, max_length: int = 60) -> str:
    """
    Generate a URL-friendly slug from the given title text.
    Port of the n8n Code node's generateSlug() JavaScript function.

    Rules (matching the n8n workflow):
      - Lowercase
      - Replace accented characters
      - Replace '&' with '-and-'
      - Replace spaces with hyphens
      - Strip non-word characters except hyphens
      - Collapse multiple hyphens
      - Truncate at word boundary to max_length
    """
    if not text:
        return ""

    slug = text.strip().lower()

    # Normalize unicode (handle accented chars like à→a, ñ→n, ç→c)
    slug = unicodedata.normalize("NFKD", slug)
    slug = slug.encode("ascii", "ignore").decode("ascii")

    # Replace ampersand
    slug = slug.replace("&", "-and-")

    # Replace spaces with hyphens
    slug = re.sub(r"\s+", "-", slug)

    # Remove all non-word chars except hyphens
    slug = re.sub(r"[^\w\-]+", "", slug)

    # Collapse multiple hyphens
    slug = re.sub(r"-{2,}", "-", slug)

    # Trim hyphens from start and end
    slug = slug.strip("-")

    # Truncate to max_length at word boundary
    if len(slug) > max_length:
        slug = slug[:max_length]
        last_hyphen = slug.rfind("-")
        if last_hyphen > 0:
            slug = slug[:last_hyphen]

    logger.info(f"🔗 Generated slug: '{slug}' from title: '{text[:50]}...'")
    return slug
