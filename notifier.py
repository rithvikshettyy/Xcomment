import smtplib
import logging
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config

logger = logging.getLogger("bot.notifier")

def send_error_email(error_message: str, traceback_details: str = None) -> bool:
    """
    Sends an error notification email via Gmail SMTP using Python's standard library.
    This call is completely non-blocking to the bot's core execution loop.
    """
    if not config.ENABLE_EMAIL_NOTIFICATIONS:
        logger.debug("Email notifications are disabled in config. Skipping notification.")
        return False
        
    if not config.GMAIL_SENDER or not config.GMAIL_APP_PASSWORD or not config.GMAIL_RECEIVER:
        logger.warning("[NOTIFIER] Missing email credentials in 'email_credentials.txt'. Cannot send alert.")
        return False
        
    try:
        logger.info(f"[NOTIFIER] Attempting to send error email to {config.GMAIL_RECEIVER}...")
        
        # 1. Setup email metadata
        msg = MIMEMultipart()
        msg["From"] = config.GMAIL_SENDER
        msg["To"] = config.GMAIL_RECEIVER
        msg["Subject"] = "🚨 CRITICAL: X Comment Bot Error Alert!"
        
        # 2. Formulate email body
        tb_content = traceback_details or traceback.format_exc()
        body = f"""
<h2>🚨 X Comment Bot Error Alert</h2>
<p>Your 24/7 X automation bot has encountered a critical event and wants to notify you.</p>

<hr/>
<p><strong>Error Message:</strong></p>
<pre style="background: #f8f9fa; padding: 10px; border-left: 4px solid #dc3545; font-family: monospace;">
{error_message}
</pre>

<p><strong>Traceback/Context:</strong></p>
<pre style="background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6; font-family: monospace; font-size: 13px; max-height: 400px; overflow-y: auto;">
{tb_content}
</pre>
<hr/>

<p style="color: #6c757d; font-size: 12px;">This is an automated notification from your local X Comment Bot running 24/7. None of your local credentials were sent or exposed.</p>
"""
        msg.attach(MIMEText(body, "html"))
        
        # 3. Connect to Gmail SMTP server
        logger.debug("Connecting to Gmail SMTP server (smtp.gmail.com:587)...")
        with smtplib.SMTP(host="smtp.gmail.com", port=587, timeout=15) as smtp:
            smtp.starttls()  # Secure the connection using TLS
            logger.debug("Authenticating with Google App Password credentials...")
            smtp.login(user=config.GMAIL_SENDER, password=config.GMAIL_APP_PASSWORD)
            
            logger.debug("Dispatching email...")
            smtp.send_message(msg)
            
        logger.info("[NOTIFIER] Error email notification successfully sent!")
        return True
        
    except Exception as e:
        logger.error(f"[NOTIFIER] Failed to send email alert: {e}")
        return False
