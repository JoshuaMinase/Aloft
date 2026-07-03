"""
Email service for sending transactional emails.

Uses Resend (https://resend.com) by default with SendGrid as an alternative.
Both have free tiers suitable for development and small-scale production.

Configuration:
  - RESEND_API_KEY: Your Resend API key (default)
  - SENDGRID_API_KEY: Your SendGrid API key (alternative)
  - FROM_EMAIL: The sender email address (must be verified in your email service)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("aloft.email")


class EmailError(Exception):
    """Raised when email sending fails."""


async def send_password_reset_email(email: str, reset_token: str, base_url: str) -> None:
    """Send a password reset email to the user.

    Args:
        email: Recipient email address
        reset_token: JWT password reset token
        base_url: Base URL of your frontend (e.g., https://aloft.app)

    Raises:
        EmailError: If email sending fails
    """
    settings = get_settings()
    
    # Construct the reset link (frontend should handle the reset flow)
    reset_link = f"{base_url}/reset-password?token={reset_token}"
    
    # Email content
    subject = "Reset your Aloft password"
    html_content = f"""
    <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>You requested a password reset for your Aloft account.</p>
            <p>Click the link below to reset your password:</p>
            <p><a href="{reset_link}">Reset Password</a></p>
            <p>This link will expire in 15 minutes.</p>
            <p>If you didn't request this password reset, you can safely ignore this email.</p>
            <p>— The Aloft Team</p>
        </body>
    </html>
    """
    
    # Try Resend first, then SendGrid as fallback
    resend_key = getattr(settings, "resend_api_key", None)
    sendgrid_key = getattr(settings, "sendgrid_api_key", None)
    from_email = getattr(settings, "from_email", "noreply@aloft.app")
    
    if resend_key:
        try:
            await _send_via_resend(email, from_email, subject, html_content, resend_key)
            logger.info(f"Password reset email sent via Resend to {email}")
            return
        except Exception as exc:
            logger.warning(f"Resend email failed, trying SendGrid: {exc}")
    
    if sendgrid_key:
        try:
            await _send_via_sendgrid(email, from_email, subject, html_content, sendgrid_key)
            logger.info(f"Password reset email sent via SendGrid to {email}")
            return
        except Exception as exc:
            logger.warning(f"SendGrid email failed: {exc}")
    
    # If no email service is configured, log the reset link for development
    logger.warning(
        "No email service configured. In production, set RESEND_API_KEY or SENDGRID_API_KEY. "
        f"Reset link for {email}: {reset_link}"
    )
    raise EmailError(
        "Email service not configured. Please set RESEND_API_KEY or SENDGRID_API_KEY in environment variables."
    )


async def _send_via_resend(
    to_email: str,
    from_email: str,
    subject: str,
    html_content: str,
    api_key: str,
) -> None:
    """Send email via Resend API."""
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
            raise EmailError(f"Resend API error: {response.status_code} - {error_detail}")


async def _send_via_sendgrid(
    to_email: str,
    from_email: str,
    subject: str,
    html_content: str,
    api_key: str,
) -> None:
    """Send email via SendGrid API."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [
                    {
                        "to": [{"email": to_email}],
                        "subject": subject,
                    }
                ],
                "from": {"email": from_email},
                "content": [
                    {
                        "type": "text/html",
                        "value": html_content,
                    }
                ],
            },
            timeout=10.0,
        )
        
        if response.status_code not in (200, 202):
            error_detail = response.text
            raise EmailError(f"SendGrid API error: {response.status_code} - {error_detail}")
