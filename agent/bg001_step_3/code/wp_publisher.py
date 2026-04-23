import os
import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def publish_to_wordpress(
    slug: str,
    title: str,
    html_content: str,
    featured_image_url: str,
) -> Optional[Dict]:
    """
    POST the blog content to the WordPress endpoint.
    Mirrors the n8n HTTP Request1 node.

    Environment variables:
      - WP_PUBLISH_URL : The WordPress publish endpoint URL
      - WP_SECRET      : The x-wp-secret header value

    Returns the JSON response from the WP endpoint, or None on failure.
    """
    wp_url = os.environ.get("WP_PUBLISH_URL", "")
    wp_secret = os.environ.get("WP_SECRET", "")
    wp_author = os.environ.get("WP_AUTHOR", "")

    if not wp_url:
        logger.error("❌ WP_PUBLISH_URL is not set in environment variables")
        return None

    if not wp_secret:
        logger.error("❌ WP_SECRET is not set in environment variables")
        return None

    headers = {
        "Accept": "application/json",
        "x-wp-secret": wp_secret,
    }

    body = {
        "slug": slug,
        "status": "publish",
        "content": html_content,
        "featured_image": featured_image_url,
        "title": title,
        "author": wp_author,
    }

    try:
        logger.info(f"📤 Publishing to WordPress: {wp_url}")
        logger.info(f"   Title: {title}")
        logger.info(f"   Slug : {slug}")

        with httpx.Client(timeout=60.0) as client:
            response = client.post(wp_url, headers=headers, json=body)

        if response.status_code in (200, 201):
            data = response.json()
            logger.info(f"✅ WordPress publish successful! Response: {response.status_code}")
            return data
        else:
            logger.error(
                f"❌ WordPress publish failed: {response.status_code} — {response.text[:500]}"
            )
            return None

    except httpx.TimeoutException:
        logger.error(f"❌ WordPress publish timed out for slug: {slug}")
        return None
    except Exception as e:
        logger.error(f"❌ WordPress publish error: {e}")
        return None
