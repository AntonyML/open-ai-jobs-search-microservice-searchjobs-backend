import logging
import httpx

logger = logging.getLogger(__name__)


async def send_admin_alert(
    email: str,
    subject: str,
    body: str,
    resend_api_key: str | None = None,
    resend_from_email: str | None = None,
):
    if not email:
        logger.warning("No admin email configured. Alert not sent.")
        logger.warning("SUBJECT: %s", subject)
        logger.warning("BODY: %s", body)
        return

    if not resend_api_key:
        logger.info("Resend not configured. Logging alert.")
        logger.warning("ALERT [%s]: %s", email, subject)
        logger.warning("BODY: %s", body)
        return

    html_body = body.replace("\n", "<br>")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"Jobs Ingest <{resend_from_email or 'onboarding@resend.dev'}>",
                    "to": [email],
                    "subject": subject,
                    "html": f"<pre>{html_body}</pre>",
                },
            )
            resp.raise_for_status()
        logger.info("Alert sent to %s: %s", email, subject)
    except Exception as e:
        logger.error("Failed to send alert to %s: %s", email, e)
