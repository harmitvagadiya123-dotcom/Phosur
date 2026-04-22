import os
import json
import logging
from typing import Optional, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)

# System prompt for packaging company relevance check
SYSTEM_PROMPT = """
Check whether the content is related to a packaging company.
 
Rules:
1. If the content contains a link related to a packaging company (such as packaging manufacturers, packaging suppliers, packaging solutions, packaging materials, sustainability in packaging, etc.), extract and return the link in JSON format.
2. If the content is NOT related to a packaging company, ignore it and return nothing or an empty JSON.
3. The output must contain only the JSON, with no explanations or extra text.

Example Output:
{ "link": "https://abcpackaging.com" }
"""

def check_packaging_relevance(content: Dict) -> Optional[str]:
    """
    Uses OpenAI to check if an RSS entry is relevant to a packaging company.
    Returns the link if relevant, else None.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found in environment.")
        return None

    client = OpenAI(api_key=api_key)
    
    prompt = f"Input: {json.dumps(content)}\n\nTask: Filter for packaging company relevance."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )

        result = json.loads(response.choices[0].message.content)
        link = result.get("link")
        
        if link:
            logger.info(f"🎯 Relevant content found: {link}")
            return link
        
        return None

    except Exception as e:
        logger.error(f"❌ OpenAI processing failed: {e}")
        return None
