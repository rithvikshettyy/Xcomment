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
        # Trim error message in subject to keep it neat
        short_err = error_message.split('\n')[0]
        if len(short_err) > 40:
            short_err = short_err[:40] + "..."
        msg["Subject"] = f"🚨 X Bot Alert: {short_err}"
        
        # 2. Formulate email body (Minimalist premium aesthetic)
        tb_content = traceback_details or traceback.format_exc()
        body = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f5f7; padding: 20px; color: #333333; line-height: 1.5; max-width: 600px; margin: 0 auto; border-radius: 8px;">
    <div style="background-color: #ffffff; padding: 24px; border-radius: 12px; border: 1px solid #e1e4e8; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
        <h2 style="margin-top: 0; color: #d9383a; font-size: 20px; font-weight: 700; border-bottom: 2px solid #f0f2f5; padding-bottom: 12px;">
            🚨 X Comment Bot Alert
        </h2>
        
        <p style="font-size: 14px; color: #4b5563; margin-top: 16px;">
            Your 24/7 X automation bot encountered an issue and has successfully recovered. Details:
        </p>
        
        <div style="background-color: #fff5f5; border-left: 4px solid #d9383a; padding: 14px; border-radius: 6px; margin: 20px 0;">
            <strong style="color: #b91c1c; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px;">
                Error Message
            </strong>
            <span style="font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 13px; color: #1f2937; word-break: break-word; font-weight: 600;">
                {error_message}
            </span>
        </div>
        
        <details style="margin-top: 20px; cursor: pointer;">
            <summary style="font-size: 13px; color: #2563eb; font-weight: 600; outline: none; margin-bottom: 8px;">
                🔍 View Technical Traceback / Context
            </summary>
            <pre style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; border-radius: 6px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 11px; color: #475569; overflow-x: auto; max-height: 250px; margin: 8px 0 0 0; line-height: 1.4;">
{tb_content}
            </pre>
        </details>
        
        <div style="margin-top: 28px; border-top: 1px solid #f0f2f5; padding-top: 16px; font-size: 11px; color: #9ca3af; text-align: center;">
            Sent automatically by X Comment Bot. Local credentials remain 100% secure.
        </div>
    </div>
</div>
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
