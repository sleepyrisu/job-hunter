import json
import urllib.parse
import urllib.request

import config


def send_telegram_message(message_text, token, chat_id):
    """Sends a formatted message to the specified Telegram Chat ID using HTML parsing."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # nosec B310
        with urllib.request.urlopen(req, timeout=15) as res:  # nosec B310
            response_body = res.read().decode("utf-8")
            response_json = json.loads(response_body)
            if response_json.get("ok"):
                print("Telegram notification pushed successfully!")
                return True
            else:
                print(f"Telegram returned error: {response_json}")
                return False
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")
        return False

def send_telegram_report(matched_jobs):
    """Formats and sends matched jobs to Telegram."""
    if not matched_jobs:
        return
        
    settings = config.load_settings()
    tg_config = settings.get("notifications", {})
    
    # Check if Telegram is enabled and configured
    if not tg_config.get("telegram_enabled"):
        print("Telegram notifications are disabled in settings.")
        return
        
    token = tg_config.get("telegram_bot_token")
    chat_id = tg_config.get("telegram_chat_id")
    
    if not token or not chat_id:
        print("WARNING: Telegram bot token or chat ID is missing. Skipping Telegram push.")
        return

    print(f"Sending {len(matched_jobs)} matched jobs to Telegram...")
    
    for job in matched_jobs:
        # Generate message body
        platform_name = job.get("platform", "").capitalize()
        score = job.get("score", 0)
        
        # HTML formatting for Telegram message
        msg = (
            f"🎯 <b>New High Match Openings ({score}%)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💼 <b>Title:</b> {job.get('title')}\n"
            f"🏢 <b>Company:</b> {job.get('company')}\n"
            f"📍 <b>Location:</b> {job.get('location')}\n"
            f"📱 <b>Platform:</b> {platform_name}\n"
            f"🔗 <a href='{job.get('url')}'>Apply Here</a>\n\n"
            f"💡 <b>Match Reason:</b>\n<i>{job.get('reason')}</i>\n"
        )
        
        # Append cover letter if exists
        cover_letter = job.get("cover_letter")
        if cover_letter:
            msg += (
                f"\n✉️ <b>Tailored Cover Letter:</b>\n"
                f"<i>(Tap to copy the block below)</i>\n"
                f"<pre><code>{cover_letter}</code></pre>"
            )
            
        send_telegram_message(msg, token, chat_id)
