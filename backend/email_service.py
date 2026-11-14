import smtplib
import os
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

HEADER_STYLE = "background:linear-gradient(135deg,#2563EB,#4f46e5);padding:28px 32px;color:#ffffff"

def _build_html(destination, alert_type, body_html):
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif'>"
        "<table width='100%' cellpadding='0' cellspacing='0'>"
        "<tr><td align='center' style='padding:30px 10px'>"
        "<table width='600' cellpadding='0' cellspacing='0' "
        "style='background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)'>"
        "<tr><td style='" + HEADER_STYLE + "'>"
        "<p style='margin:0 0 4px;font-size:13px;opacity:0.8'>AI Trip Planner Alert</p>"
        "<h1 style='margin:0;font-size:22px'>" + escape(str(destination)) + "</h1>"
        "<p style='margin:6px 0 0;font-size:15px;opacity:0.9'>" + escape(str(alert_type)) + "</p>"
        "</td></tr>"
        "<tr><td style='padding:28px 32px;color:#111827;font-size:15px;line-height:1.6'>"
        + body_html +
        "</td></tr>"
        "<tr><td style='padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb'>"
        "<p style='margin:0;font-size:12px;color:#9ca3af'>"
        "You saved this trip for monitoring in AI Trip Planner. Checks run every 6 hours."
        "</p></td></tr>"
        "</table></td></tr></table></body></html>"
    )

def send_alert(to_email, destination, alert_type, body_html):
    sender   = os.getenv("GMAIL_SENDER", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    if not sender or not password:
        print("Email not configured. Set GMAIL_SENDER and GMAIL_APP_PASSWORD in .env")
        return False
    html = _build_html(destination, alert_type, body_html)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "AI Trip Planner: " + alert_type + " — " + destination
    msg["From"]    = "AI Trip Planner <" + sender + ">"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
        print("Alert sent to " + to_email + ": " + alert_type)
        return True
    except smtplib.SMTPAuthenticationError:
        print("Gmail auth failed. Check GMAIL_SENDER and GMAIL_APP_PASSWORD in .env")
        return False
    except Exception as e:
        print("Email error: " + str(e))
        return False

def send_test_email(to_email, weather_enabled=True, events_enabled=True):
    enabled = []
    if weather_enabled:
        enabled.append("significant live forecast changes for your saved trip dates")
    if events_enabled:
        enabled.append("new or changed local event information")
    if enabled:
        items = "".join("<li>" + escape(item) + "</li>" for item in enabled)
        body = ("<p>Your trip was saved and email delivery was tested successfully.</p>"
                "<p>You enabled these alert types:</p><ul>" + items + "</ul>"
                "<p>Checks run every <strong>6 hours while the backend service is running</strong>. "
                "Delivery is subject to provider availability.</p>")
    else:
        body = "<p>Your trip was saved. Automatic weather and event alerts are disabled.</p>"
    return send_alert(to_email, "Setup Test", "Trip Save Confirmation", body)
