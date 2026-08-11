"""
Job Alert System - sends notifications for new matching jobs.
Supports email and Telegram.
"""
import json
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def load_alert_config():
    """Load alert configuration from settings."""
    config_path = os.path.join(DIRECTORY, "settings.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            settings = json.load(f)
            return settings.get("alerts", {})
    return {}


def send_email_alert(jobs, recipient_email, smtp_config=None):
    """
    Send email alert with new matching jobs.
    """
    if not smtp_config:
        smtp_config = {
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "",
            "password": "",
        }

    if not smtp_config.get("username") or not smtp_config.get("password"):
        print("Email not configured - skipping email alert")
        return False

    # Build email content
    subject = f"Job Alert: {len(jobs)} new matching jobs found - {datetime.now().strftime('%Y-%m-%d')}"

    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .job-card {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .job-title {{ font-size: 16px; font-weight: bold; color: #333; }}
            .company {{ color: #666; }}
            .score {{ color: #28a745; font-weight: bold; }}
            .location {{ color: #888; }}
            .reason {{ font-size: 12px; color: #666; margin-top: 5px; }}
        </style>
    </head>
    <body>
        <h2>New Matching Jobs Found</h2>
        <p>We found <strong>{len(jobs)}</strong> new jobs matching your profile:</p>
    """

    for job in jobs[:10]:  # Show top 10
        score = job.get("score", 0)
        score_class = "score" if score >= 70 else ""
        html_content += f"""
        <div class="job-card">
            <div class="job-title">{job.get('title', 'Unknown')}</div>
            <div class="company">{job.get('company', 'Unknown')}</div>
            <div class="location">{job.get('location', 'Unknown')}</div>
            <div class="{score_class}">Score: {score}/100</div>
            <div class="reason">{job.get('reason', '')}</div>
            <a href="{job.get('url', '#')}">View Job</a>
        </div>
        """

    html_content += """
        <p>Visit the dashboard to view all jobs and apply.</p>
    </body>
    </html>
    """

    # Send email
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_config["username"]
        msg["To"] = recipient_email

        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
            server.starttls()
            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg)

        print(f"Email alert sent to {recipient_email}")
        return True

    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_telegram_alert(jobs, bot_token, chat_id):
    """
    Send Telegram alert with new matching jobs.
    """
    import urllib.request

    if not bot_token or not chat_id:
        print("Telegram not configured - skipping alert")
        return False

    # Build message
    message = f"*New Job Alert*\n\nFound {len(jobs)} matching jobs:\n\n"

    for job in jobs[:5]:  # Show top 5 in Telegram
        score = job.get("score", 0)
        message += f"*{job.get('title', 'Unknown')}*\n"
        message += f"Company: {job.get('company', 'Unknown')}\n"
        message += f"Location: {job.get('location', 'Unknown')}\n"
        message += f"Score: {score}/100\n"
        message += f"[View Job]({job.get('url', '#')})\n\n"

    # Send via Telegram API
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }).encode("utf-8")

        # Fixed Telegram API endpoint; body is JSON without user-supplied URLs.
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})  # nosec B310
        with urllib.request.urlopen(req) as response:  # nosec B310
            result = json.loads(response.read())
            if result.get("ok"):
                print("Telegram alert sent")
                return True
            else:
                print(f"Telegram error: {result}")
                return False

    except Exception as e:
        print(f"Failed to send Telegram: {e}")
        return False


def check_and_send_alerts(new_jobs):
    """Check if alerts should be sent and send them."""
    config = load_alert_config()

    if not config.get("enabled", False):
        return

    # Email alert
    email_config = config.get("email", {})
    if email_config.get("enabled") and email_config.get("recipient"):
        smtp_config = {
            "host": email_config.get("smtp_host", "smtp.gmail.com"),
            "port": email_config.get("smtp_port", 587),
            "username": email_config.get("username", ""),
            "password": email_config.get("password", ""),
        }
        send_email_alert(new_jobs, email_config["recipient"], smtp_config)

    # Telegram alert
    telegram_config = config.get("telegram", {})
    if telegram_config.get("enabled") and telegram_config.get("bot_token"):
        send_telegram_alert(
            new_jobs,
            telegram_config["bot_token"],
            telegram_config["chat_id"]
        )


if __name__ == "__main__":
    # Test alert system
    test_jobs = [
        {
            "title": "Junior RPA Developer",
            "company": "Intel Malaysia",
            "location": "Penang, Malaysia",
            "score": 85,
            "reason": "技能匹配(+25) | Junior岗位(+10) | Penang(+10)",
            "url": "https://example.com/job/1"
        }
    ]

    print("Testing alert system...")
    print("Email configured:", bool(load_alert_config().get("email", {}).get("enabled")))
    print("Telegram configured:", bool(load_alert_config().get("telegram", {}).get("enabled")))
