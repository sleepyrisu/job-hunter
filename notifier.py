import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


def generate_html_content(matched_jobs):
    """Generates the modern HTML page summarizing the matched job openings."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    job_cards = ""
    
    for job in matched_jobs:
        # Score Badge Color based on match quality
        score = job["score"]
        if score >= 90:
            badge_color = "#10b981" # Green
        elif score >= 80:
            badge_color = "#3b82f6" # Blue
        else:
            badge_color = "#f59e0b" # Amber
            
        platform_name = job["platform"].capitalize()
        
        job_cards += f"""
        <div class="card">
            <div class="card-header">
                <div>
                    <h2 class="job-title"><a href="{job['url']}" target="_blank">{job['title']}</a></h2>
                    <p class="job-company">{job['company']} — <span class="job-location">{job['location']}</span></p>
                </div>
                <div class="score-badge" style="background-color: {badge_color};">
                    {score}%
                </div>
            </div>
            <div class="card-body">
                <span class="platform-tag">{platform_name}</span>
                <p class="ai-reason"><strong>AI Match Reason:</strong> {job['reason']}</p>
            </div>
            <div class="card-footer">
                <a class="btn" href="{job['url']}" target="_blank">View & Apply on {platform_name}</a>
            </div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🎯 AI Job Match Report - {date_str}</title>
        <style>
            body {{
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                background-color: #f8fafc;
                margin: 0;
                padding: 0;
                color: #334155;
            }}
            .container {{
                max-width: 600px;
                margin: 20px auto;
                background-color: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
                border: 1px solid #e2e8f0;
            }}
            .header {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                color: #ffffff;
                padding: 30px 20px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 700;
                letter-spacing: -0.025em;
            }}
            .header p {{
                margin: 5px 0 0 0;
                font-size: 14px;
                color: #94a3b8;
            }}
            .content {{
                padding: 20px;
            }}
            .card {{
                background-color: #ffffff;
                border: 1px solid #f1f5f9;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 20px;
                box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.05);
            }}
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 12px;
            }}
            .job-title {{
                margin: 0;
                font-size: 18px;
                font-weight: 600;
                line-height: 1.25;
            }}
            .job-title a {{
                color: #0f172a;
                text-decoration: none;
            }}
            .job-title a:hover {{
                color: #3b82f6;
                text-decoration: underline;
            }}
            .job-company {{
                margin: 4px 0 0 0;
                font-size: 14px;
                color: #64748b;
            }}
            .job-location {{
                font-style: italic;
            }}
            .score-badge {{
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                padding: 6px 10px;
                border-radius: 20px;
                text-align: center;
                min-width: 35px;
                margin-left: 10px;
                display: inline-block;
            }}
            .card-body {{
                margin-bottom: 12px;
            }}
            .platform-tag {{
                display: inline-block;
                background-color: #f1f5f9;
                color: #475569;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 8px;
                border-radius: 4px;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}
            .ai-reason {{
                margin: 0;
                font-size: 13px;
                line-height: 1.5;
                color: #475569;
                background-color: #fcfdfd;
                border-left: 3px solid #cbd5e1;
                padding: 8px 12px;
                border-radius: 0 4px 4px 0;
            }}
            .card-footer {{
                text-align: right;
            }}
            .btn {{
                display: inline-block;
                background-color: #0f172a;
                color: #ffffff !important;
                text-decoration: none;
                font-size: 13px;
                font-weight: 500;
                padding: 8px 14px;
                border-radius: 6px;
                transition: background-color 0.2s;
            }}
            .btn:hover {{
                background-color: #334155;
            }}
            .footer {{
                background-color: #f8fafc;
                text-align: center;
                padding: 20px;
                font-size: 12px;
                color: #94a3b8;
                border-top: 1px solid #f1f5f9;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 AI Job Hunter Match Report</h1>
                <p>Curated just for you on {date_str}</p>
            </div>
            <div class="content">
                {job_cards}
            </div>
            <div class="footer">
                <p>This report was automatically generated by AI Job Hunter.</p>
                <p>Configured in your local job hunter directory.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

def save_local_html_report(matched_jobs):
    """Saves the matched jobs report to a local HTML file."""
    if not matched_jobs:
        return False
        
    html_content = generate_html_content(matched_jobs)
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matched_jobs.html")
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Local HTML report generated successfully at: {output_path}")
        return True
    except Exception as e:
        print(f"Error saving local HTML report: {e}")
        return False

def send_email_report(matched_jobs):
    """Sends an email containing the curated job listings."""
    if not matched_jobs:
        print("No new highly matched jobs to report.")
        return False
        
    settings = config.load_settings()
    if not settings["notifications"]["email_enabled"]:
        print("Email notifications are disabled in settings.")
        return False

    sender = settings["notifications"]["email_sender"]
    password = settings["notifications"]["email_password"]
    receiver = settings["notifications"]["email_receiver"]
    
    if not sender or not password:
        print("WARNING: Email SMTP configurations are missing. Skipping email report.")
        print(f"Would have emailed {len(matched_jobs)} matched jobs:")
        for job in matched_jobs:
            print(f"- {job['title']} at {job['company']} (Score: {job['score']}%): {job['url']}")
        return False

    # Create Message
    msg = MIMEMultipart("alternative")
    date_str = datetime.now().strftime("%Y-%m-%d")
    msg["Subject"] = f"🎯 [AI Job Hunter] {len(matched_jobs)} New Match Report - {date_str}"
    msg["From"] = sender
    msg["To"] = receiver

    html_content = generate_html_content(matched_jobs)

    try:
        # SMTP setup
        server = smtplib.SMTP("smtp.gmail.com", 587) # Defaulting to Gmail SMTP
        server.starttls()
        server.login(sender, password)
        
        # Attach HTML
        msg.attach(MIMEText(html_content, "html"))
        
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        print("Match report email sent successfully!")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
