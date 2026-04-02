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

def send_assessment_email(to_email: str, candidate_name: str, position_title: str, assessment_url: str, time_limit: int):
    """
    Sends an actual email to the candidate with the psychometric assessment link.
    Requires SMTP credentials in the environment.
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("\n⚠️ [WARNING] SMTP_USERNAME or SMTP_PASSWORD not found in .env.")
        print(f"⚠️ Could not send real email to {to_email}. Please add credentials.")
        return
    
    msg = EmailMessage()
    msg['Subject'] = f"Technical Assessment Invitation: {position_title}"
    msg['From'] = f"HireHand AI <{SMTP_USERNAME}>"
    msg['To'] = to_email
    
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-w-2xl mx-auto p-4 border border-gray-200 rounded-lg">
            <h2 style="color: #4F46E5;">EOS-IA Psychometric Assessment</h2>
            <p>Dear <strong>{candidate_name}</strong>,</p>
            <p>As part of the evaluation process for the <strong>{position_title}</strong> role, please complete the following technical assessment.</p>
            <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                <p style="margin: 0; font-size: 16px;"><strong>Time Limit:</strong> {time_limit} Minutes</p>
                <p style="margin: 10px 0 0 0; font-size: 16px;">
                    <strong>Assessment Link:</strong> <a href="{assessment_url}" style="color: #2563eb; font-weight: bold;">Begin Assessment Here</a>
                </p>
            </div>
            <p style="color: #d97706; font-size: 14px;"><strong>Note:</strong> Once you begin, a strict timer will start. The assessment will automatically submit when time is up. Please ensure you have a stable internet connection.</p>
            <p>Best of luck!</p>
            <br/>
            <p style="font-size: 14px; color: #666;">Regards,<br/>HireHand Hiring Team</p>
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
        print(f"✅ Real assessment email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send real email: {e}")
def send_shortlisted_email(to_email: str, candidate_name: str, position_title: str):
    """
    Sends a shortlisted email to the candidate.
    Requires SMTP credentials in the environment.
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("\n⚠️ [WARNING] SMTP_USERNAME or SMTP_PASSWORD not found in .env.")
        print(f"⚠️ Could not send real email to {to_email}. Please add credentials.")
        return
    
    msg = EmailMessage()
    msg['Subject'] = f"Update on your application: {position_title}"
    msg['From'] = f"HireHand AI <{SMTP_USERNAME}>"
    msg['To'] = to_email
    
    # HTML Email body for a professional look
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-w-2xl mx-auto p-4 border border-gray-200 rounded-lg">
            <h2 style="color: #4F46E5;">Application Shortlisted</h2>
            <p>Dear <strong>{candidate_name}</strong>,</p>
            <p>We are pleased to inform you that your profile has been <strong>shortlisted</strong> for the <strong>{position_title}</strong> position.</p>
            <p>Our hiring team was very impressed with your background and skills. We will be reaching out to you shortly with the next steps, which may include an interview schedule or further assessments.</p>
            <p>Congratulations, and we look forward to exploring your potential with us!</p>
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

def send_rejection_email(to_email: str, candidate_name: str, position_title: str):
    """
    Sends a rejection/unselected email to the candidate.
    Requires SMTP credentials in the environment.
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("\n⚠️ [WARNING] SMTP_USERNAME or SMTP_PASSWORD not found in .env.")
        print(f"⚠️ Could not send real email to {to_email}. Please add credentials.")
        return
    
    msg = EmailMessage()
    msg['Subject'] = f"Update on your application: {position_title}"
    msg['From'] = f"HireHand AI <{SMTP_USERNAME}>"
    msg['To'] = to_email
    
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-w-2xl mx-auto p-4 border border-gray-200 rounded-lg">
            <h2 style="color: #4F46E5;">Application Update</h2>
            <p>Dear <strong>{candidate_name}</strong>,</p>
            <p>Thank you very much for your interest in the <strong>{position_title}</strong> position and for taking the time to apply.</p>
            <p>After carefully reviewing your profile along with the other applications, we regret to inform you that we will not be moving forward with your candidacy at this time. This was a difficult decision, as we received many strong applications.</p>
            <p>We truly appreciate the time and effort you put into your application and wish you the absolute best in your future endeavors.</p>
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

def send_password_reset_email(to_email: str, candidate_name: str, reset_link: str):
    """
    Sends a password reset email.
    Requires SMTP credentials in the environment.
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("\n⚠️ [WARNING] SMTP_USERNAME or SMTP_PASSWORD not found in .env.")
        print(f"⚠️ Could not send real email to {to_email}. Please add credentials.")
        return
    
    msg = EmailMessage()
    msg['Subject'] = "Reset Your Password - HireHand AI"
    msg['From'] = f"HireHand AI <{SMTP_USERNAME}>"
    msg['To'] = to_email
    
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-w-2xl mx-auto p-4 border border-gray-200 rounded-lg">
            <h2 style="color: #4F46E5;">Password Reset Request</h2>
            <p>Hi <strong>{candidate_name}</strong>,</p>
            <p>We received a request to reset your password for your HireHand AI account.</p>
            <p>Click the button below to set a new password. This link will expire in 15 minutes.</p>
            <div style="margin: 25px 0;">
                <a href="{reset_link}" style="background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Reset Password</a>
            </div>
            <p style="font-size: 14px; color: #666;">If you didn't request a password reset, you can safely ignore this email.</p>
            <br/>
            <p style="font-size: 14px; color: #666;">Best regards,<br/>HireHand Team</p>
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
        print(f"✅ Password reset email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send password reset email: {e}")
