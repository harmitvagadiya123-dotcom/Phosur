"""
spam_classifier.py — Classifies incoming emails as Valid, Spam, or Scam.

Replicates AI Agent 6 from the n8n Autoresponder workflow.
Uses OpenRouter (openai/gpt-4o-mini) via the OpenAI client.
"""
import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a highly advanced email security filter designed to analyze emails for potential threats such as spam, scams, viruses, and phishing attempts for a packaging manufacturing and export company. Your primary goal is to detect malicious and spam emails by thoroughly inspecting email content, sender details, and attachments. Additionally, you will only categorize emails as Valid if they are sent with the clear intention to buy packaging products or services from the company. Out of Office replies will be categorized as Spam and handled appropriately.

Detection Criteria:

Valid Email Criteria
Intent to Purchase Packaging:
- The email explicitly expresses interest in buying packaging products or services.
- Includes clear packaging specifications, inquiries about pricing, MOQ, materials, customization, samples, or lead times.
- Mentions specific packaging needs (boxes, cartons, bags, branded packaging, export services).

Sender Details:
- Sender details align with legitimate business or personal email addresses (gmail is ok).

Out of Office Reply Detection (Spam):
- Common phrases in the subject line or content, such as: "Out of Office," "Auto-Reply," "I am currently unavailable," or similar.
- Automated language patterns: "I will respond to your email when I return."

Attachment Inspection (Scam):
- Attachments with .zip or .7z formats.
- Files with double extensions (e.g., invoice.pdf.exe).

Sender Email & Domain Verification (Scam):
- Spoofed domains (e.g., @paypa1.com instead of @paypal.com).

Spam Indicators:
- Emails from Alibaba, social media platforms, or advertisement platforms.
- Marketing emails from unrelated companies.
- Subject line containing the word "spam".
- Generic or sensational subject lines.

Scam Indicators:
- Urgency-based language: "ASAP," "Immediate response required."
- Sender email does not match signature details.
- Suspicious links (bit.ly, tinyurl.com, .xyz, .click domains).

Valid mail examples (packaging inquiries):
1] "What is your minimum order quantity?" → Valid
2] "Can you help with packaging for cosmetics?" → Valid
3] "Do you offer sustainable packaging?" → Valid

Invalid mail examples (scams/spam):
1] "Please find the attached purchase file. [ATTACHMENT: order.zip]" → Scam
2] Out of Office auto-reply → Spam

IMPORTANT: Return ONLY one word: Valid, Spam, or Scam. Nothing else."""


def classify_email(
    html_content: str,
    subject: str,
    sender_address: str,
) -> str:
    """
    Classifies an email as 'Valid', 'Spam', or 'Scam'.
    Returns one of those three strings.
    Defaults to 'Spam' on any error.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.error("❌ OPENROUTER_API_KEY not set")
        return "Spam"

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    user_prompt = (
        f"Email Subject: {subject}\n"
        f"Sender Address: {sender_address}\n"
        f"Email Content:\n{html_content[:3000]}"
    )

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=10,
            temperature=0,
        )
        result = response.choices[0].message.content.strip()
        # Normalise to exactly Valid/Spam/Scam
        for label in ("Valid", "Spam", "Scam"):
            if label.lower() in result.lower():
                logger.info(f"🔍 Spam classifier result: {label} | Subject: {subject[:60]}")
                return label
        logger.warning(f"⚠️ Unexpected classifier output: {result!r} — defaulting to Spam")
        return "Spam"
    except Exception as e:
        logger.error(f"❌ Spam classification failed: {e}", exc_info=True)
        return "Spam"
