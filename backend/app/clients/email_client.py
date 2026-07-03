"""
Email client for sending transactional emails via Resend.

Resend: https://resend.com/ - Free tier: 3,000 emails/month
Alternative: SendGrid (not implemented here, use email_service.py for both)

Configuration:
  - RESEND_API_KEY: Your Resend API key
  - FROM_EMAIL: The sender email address (must be verified in Resend dashboard)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("aloft.email_client")


class EmailError(Exception):
    """Raised when email sending fails."""


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
) -> None:
    """Send an email via Resend API.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML body content

    Raises:
        EmailError: If email sending fails
    """
    settings = get_settings()
    api_key = settings.resend_api_key
    from_email = settings.from_email

    if not api_key:
        raise EmailError(
            "RESEND_API_KEY not configured. Set it in your environment variables. "
            "Get a free key at https://resend.com/"
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            },
            timeout=10.0,
        )

        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"Resend API error: {response.status_code} - {error_detail}")
            raise EmailError(f"Failed to send email: {response.status_code} - {error_detail}")

        logger.info(f"Email sent successfully to {to_email}")
