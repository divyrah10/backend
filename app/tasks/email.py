from app.core.celery_app import celery_app
from app.core.config import settings
import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _send_email(recipient: str, subject: str, body: str) -> bool:
    if not settings.SMTP_HOST:
        logger.warning("SMTP is not configured; skipped email to %s", recipient)
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as client:
        if settings.SMTP_USE_TLS:
            client.starttls()
        if settings.SMTP_USERNAME:
            client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        client.send_message(message)
    return True


@celery_app.task(bind=True, max_retries=3)
def send_order_confirmation(self, order_id: str, email: str):
    """Send order confirmation email"""
    try:
        logger.info(f"Sending order confirmation for order {order_id} to {email}")
        sent = _send_email(email, f"Order {order_id} confirmed", f"Thank you for your order. Your reference is {order_id}.")
        return {"sent": sent}
    except Exception as e:
        logger.error(f"Failed to send order confirmation: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def send_shipping_notification(self, order_id: str, email: str, tracking_number: str):
    """Send shipping notification email"""
    try:
        logger.info(f"Sending shipping notification for order {order_id} to {email}")
        sent = _send_email(email, f"Order {order_id} has shipped", f"Your order is on its way. Tracking reference: {tracking_number}")
        return {"sent": sent}
    except Exception as e:
        logger.error(f"Failed to send shipping notification: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def send_password_reset(self, email: str, reset_token: str):
    """Send password reset email"""
    try:
        logger.info(f"Sending password reset email to {email}")
        sent = _send_email(email, "Reset your NOT JUST DARK password", f"Use this secure token to reset your password: {reset_token}")
        return {"sent": sent}
    except Exception as e:
        logger.error(f"Failed to send password reset: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def send_welcome_email(self, email: str, name: str):
    """Send welcome email to new users"""
    try:
        logger.info(f"Sending welcome email to {email}")
        sent = _send_email(email, "Welcome to NOT JUST DARK", f"Welcome, {name}. Your account is ready.")
        return {"sent": sent}
    except Exception as e:
        logger.error(f"Failed to send welcome email: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def send_low_stock_alert(self, product_name: str, current_stock: int, admin_emails: list):
    """Send low stock alert to admins"""
    try:
        logger.info(f"Sending low stock alert for {product_name} (stock: {current_stock})")
        results = {
            email: _send_email(
                email,
                f"Low stock: {product_name}",
                f"{product_name} has {current_stock} unit(s) remaining.",
            )
            for email in admin_emails
        }
        return {"sent": results}
    except Exception as e:
        logger.error(f"Failed to send low stock alert: {e}")
        raise self.retry(exc=e, countdown=60)
