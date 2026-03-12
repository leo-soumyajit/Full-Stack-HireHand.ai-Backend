import smtplib
from email.message import EmailMessage
import os

# To make this work, the user MUST set SMTP_USERNAME and SMTP_PASSWORD in their .env
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

def send_interview_email(to_email: str, candidate_name: str, position_title: str, scheduled_time_ist: str, meeting_link: str):
    """
    Sends an actual email to the candidate with the interview details.
    Requires SMTP credentials in the environment.
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("\n⚠️ [WARNING] SMTP_USERNAME or SMTP_PASSWORD not found in .env.")
        print(f"⚠️ Could not send real email to {to_email}. Please add credentials.")
        return
    
    msg = EmailMessage()
    msg['Subject'] = f"Interview Invitation: {position_title}"
    msg['From'] = f"HireHand AI <{SMTP_USERNAME}>"
    msg['To'] = to_email
    
    # HTML Email body for a professional look
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-w-2xl mx-auto p-4 border border-gray-200 rounded-lg">
            <h2 style="color: #4F46E5;">Interview Invitation</h2>
            <p>Dear <strong>{candidate_name}</strong>,</p>
            <p>We are pleased to invite you to an interview for the <strong>{position_title}</strong> position.</p>
            <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                <p style="margin: 0; font-size: 16px;"><strong>Scheduled Time:</strong> {scheduled_time_ist}</p>
                <p style="margin: 10px 0 0 0; font-size: 16px;">
                    <strong>Meeting Link:</strong> <a href="{meeting_link}" style="color: #2563eb;">Join Video Interview</a>
                </p>
            </div>
            <p>Please ensure you are in a quiet environment with a stable internet connection.</p>
            <p>Looking forward to speaking with you!</p>
            <br/>
            <p style="font-size: 14px; color: #666;">Best regards,<br/>HireHand Hiring Team</p>
        </div>
      </body>
    </html>
    """
    
    msg.set_content("Please enable HTML to view this message.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"✅ Real email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send real email: {e}")
