import os
import resend

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "HireHand AI <updates@soumyajitbanerjee.in>")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

def send_interview_email(to_email: str, candidate_name: str, position_title: str, scheduled_time_ist: str, meeting_link: str):
    """
    Sends an email to the candidate with the interview details using Resend API.
    """
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent Interview Email to {to_email}")
        return
    
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
    
    try:
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": f"Interview Invitation: {position_title}",
            "html": html_content
        })
        print(f"✅ Resend: Interview email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Resend: Failed to send interview email: {e}")


def send_verification_email(to_email: str, otp: str, name: str):
    """
    Sends an OTP verification email using Resend API.
    """
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent OTP {otp} to {to_email}")
        return
        
    html_content = f"""
    <html>
      <body style="font-family: 'Inter', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #fafafa; padding: 20px;">
        <div style="max-w-xl mx-auto p-8 border border-gray-100 rounded-2xl bg-white shadow-sm">
            <h2 style="color: #4F46E5; margin-top: 0;">Identity Verification</h2>
            <p>Hi <strong>{name}</strong>,</p>
            <p>Welcome to <strong>HireHand AI</strong>! To complete your registration and secure your account, please enter the following 6-digit verification code:</p>
            
            <div style="background-color: #f8fafc; border: 1px dashed #cbd5e1; padding: 24px; border-radius: 12px; margin: 30px 0; text-align: center;">
                <p style="margin: 0; font-size: 32px; font-weight: 800; letter-spacing: 6px; color: #0f172a;">{otp}</p>
            </div>
            
            <p style="color: #64748b; font-size: 14px;">If you didn't attempt to create an account, you can safely ignore this email.</p>
            <br/>
            <p style="font-size: 14px; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 20px;">
              Securely,<br/>
              <strong>HireHand System AI</strong>
            </p>
        </div>
      </body>
    </html>
    """
    
    try:
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": "Verify your HireHand AI Account",
            "html": html_content
        })
        print(f"✅ Resend: OTP email sent to {to_email}")
    except Exception as e:
        print(f"❌ Resend: Failed to send OTP email: {e}")


def send_assessment_email(to_email: str, candidate_name: str, position_title: str, assessment_url: str, time_limit: int):
    """
    Sends an email to the candidate with the psychometric assessment link using Resend.
    """
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent Assessment to {to_email}")
        return
        
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-w-2xl mx-auto p-4 border border-gray-200 rounded-lg">
            <h2 style="color: #4F46E5;">Pre-Interview Assessment Invitation</h2>
            <p>Dear <strong>{candidate_name}</strong>,</p>
            <p>Thank you for applying for the <strong>{position_title}</strong> position.</p>
            <p>Before we proceed to the technical interview, we would like you to complete a brief Psychometric & Cognitive Assessment.</p>
            <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                <p style="margin: 0; font-size: 16px;"><strong>Time Limit:</strong> {time_limit} Minutes</p>
                <p style="margin: 10px 0 0 0; font-size: 16px;">
                    <strong>Assessment Link:</strong> <a href="{assessment_url}" style="color: #2563eb;">Start Your Assessment Here</a>
                </p>
            </div>
            <p>Please note that once you start the assessment, the timer cannot be paused. Ensure you are in a quiet environment.</p>
            <br/>
            <p style="font-size: 14px; color: #666;">Best regards,<br/>HireHand Hiring Team</p>
        </div>
      </body>
    </html>
    """
    
    try:
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": f"Required Assessment: {position_title}",
            "html": html_content
        })
        print(f"✅ Resend: Assessment email sent to {to_email}")
    except Exception as e:
        print(f"❌ Resend: Failed to send Assessment email: {e}")


def send_password_reset_email(to_email: str, reset_link: str, name: str):
    """
    Sends a Password Reset email using Resend API.
    """
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent Password Reset to {to_email}")
        return
        
    html_content = f"""
    <html>
      <body style="font-family: 'Inter', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #fafafa; padding: 20px;">
        <div style="max-w-xl mx-auto p-8 border border-gray-100 rounded-2xl bg-white shadow-sm">
            <h2 style="color: #4F46E5; margin-top: 0;">Password Reset Request</h2>
            <p>Hi <strong>{name}</strong>,</p>
            <p>We received a request to reset your password for your <strong>HireHand AI</strong> account. Click the button below to choose a new password:</p>
            
            <div style="margin: 30px 0; text-align: center;">
                <a href="{reset_link}" style="display: inline-block; background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600;">Reset Password</a>
            </div>
            
            <p style="color: #64748b; font-size: 14px;">This link will expire in 2 hours. If you didn't request a password reset, you can safely ignore this email.</p>
            <br/>
            <p style="font-size: 14px; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 20px;">
              Securely,<br/>
              <strong>HireHand System AI</strong>
            </p>
        </div>
      </body>
    </html>
    """
    
    try:
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": "Reset your HireHand AI Password",
            "html": html_content
        })
        print(f"✅ Resend: Password Reset email sent to {to_email}")
    except Exception as e:
        print(f"❌ Resend: Failed to send Password Reset email: {e}")


def send_invite_email(to_email: str, company_name: str, position_title: str, jitsi_link: str, scheduled_at_ist: str, jd_details: str):
    """
    Sends an invitation email (used broadly for outside workflows if needed) using Resend.
    """
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent invite to {to_email}")
        return

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-w-2xl mx-auto p-4 border border-gray-200 rounded-lg">
            <h2 style="color: #4F46E5;">Interview Invitation from {company_name}</h2>
            <p>You have been invited to an interview for the position of <strong>{position_title}</strong>.</p>
            <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                <p style="margin: 0; font-size: 16px;"><strong>Scheduled Time:</strong> {scheduled_at_ist}</p>
                <p style="margin: 10px 0 0 0; font-size: 16px;">
                    <strong>Join Interview:</strong> <a href="{jitsi_link}" style="color: #2563eb;">Click here to join</a>
                </p>
            </div>
            <p><strong>Job Details:</strong></p>
            <p style="white-space: pre-wrap; font-size: 14px; background: #fafafa; padding: 10px; border: 1px solid #eee;">{jd_details[:500]}...</p>
            <p>Looking forward to speaking with you!</p>
            <br/>
            <p style="font-size: 14px; color: #666;">Best regards,<br/>HireHand Team</p>
        </div>
      </body>
    </html>
    """

    try:
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": f"Interview Invitation: {position_title}",
            "html": html_content
        })
        print(f"✅ Resend: Invite email sent to {to_email}")
    except Exception as e:
        print(f"❌ Resend: Failed to send invite email: {e}")

def send_shortlisted_email(to_email: str, candidate_name: str, position_title: str):
    if not RESEND_API_KEY:
        print(f"⚠️ Fake-sent Shortlisted Email to {to_email}")
        return
    html_content = f'<html><body style="font-family: Arial; color: #333;"><div style="max-w-2xl mx-auto p-4 border rounded-lg"><h2 style="color: #4F46E5;">Application Update: Shortlisted!</h2><p>Dear <strong>{candidate_name}</strong>,</p><p>Congratulations! You have been shortlisted for the <strong>{position_title}</strong> position.</p><p>Our team will reach out shortly for the next steps.</p><br/><p>Best regards,<br/>HireHand Team</p></div></body></html>'
    try:
        resend.Emails.send({'from': RESEND_FROM_EMAIL, 'to': to_email, 'subject': f'Application Shortlisted: {position_title}', 'html': html_content})
        print(f'✅ Resend: Shortlisted email sent to {to_email}')
    except Exception as e:
        print(f'❌ Resend: Failed to send shortlisted email: {e}')

def send_rejection_email(to_email: str, candidate_name: str, position_title: str):
    if not RESEND_API_KEY:
        print(f"⚠️ Fake-sent Rejection Email to {to_email}")
        return
    html_content = f'<html><body style="font-family: Arial; color: #333;"><div style="max-w-2xl mx-auto p-4 border rounded-lg"><h2 style="color: #4F46E5;">Application Update</h2><p>Dear <strong>{candidate_name}</strong>,</p><p>Thank you for your interest in the <strong>{position_title}</strong> position.</p><p>After careful review, we will not be moving forward with your application at this time.</p><br/><p>Best regards,<br/>HireHand Team</p></div></body></html>'
    try:
        resend.Emails.send({'from': RESEND_FROM_EMAIL, 'to': to_email, 'subject': f'Update on your application: {position_title}', 'html': html_content})
        print(f'✅ Resend: Rejection email sent to {to_email}')
    except Exception as e:
        print(f'❌ Resend: Failed to send rejection email: {e}')

def send_interview_report_email(
    to_email: str,
    subject: str,
    message_body: str,
    candidate_name: str,
    position_title: str,
    sender_name: str,
    sender_email: str,
    company_name: str,
    pdf_base64: str
):
    """
    Sends an Interview Intelligence report as a PDF attachment with a customized HTML body.
    """
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent Report to {to_email}")
        return

    # User wanted a specific email sender for reports
    REPORTS_FROM_EMAIL = os.getenv("RESEND_REPORTS_EMAIL", "HireHand Reports <reports@soumyajitbanerjee.in>")

    # Render a premium Animated HTML email
    html_content = f"""
    <html>
      <head>
        <style>
          body {{ font-family: 'Inter', Helvetica, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #334155; }}
          .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1); border: 1px solid #f1f5f9; }}
          .header {{ background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%); padding: 30px; text-align: center; color: white; }}
          .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
          .header p {{ margin: 8px 0 0 0; font-size: 14px; opacity: 0.9; }}
          .content {{ padding: 40px 30px; }}
          .info-card {{ background-color: #f1f5f9; border-radius: 12px; padding: 20px; margin-bottom: 30px; text-align: left; display: flex; flex-direction: column; gap: 10px; }}
          .info-row {{ display: flex; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; font-size: 14px; }}
          .info-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
          .message-box {{ background-color: #fef8eb; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 4px 12px 12px 4px; margin-bottom: 30px; font-size: 15px; line-height: 1.6; color: #78350f; white-space: pre-wrap; }}
          .footer {{ background-color: #f8fafc; padding: 20px 30px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 12px; color: #94a3b8; }}
          .sender-pill {{ display: inline-block; background-color: #e0e7ff; color: #4338ca; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-top: 20px; }}
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>Interview Intelligence Report</h1>
            <p>AI-Generated Assessment & Insights</p>
          </div>
          <div class="content">
            <p style="font-size: 16px; margin-top: 0;">Hi there,</p>
            <p style="font-size: 16px; margin-bottom: 30px;">Attached is the detailed <strong>HireHand AI</strong> interview report for {candidate_name}.</p>
            
            <div class="info-card">
              <div class="info-row">
                <strong style="color: #64748b;">Candidate</strong>
                <span style="font-weight: 600; color: #0f172a;">{candidate_name}</span>
              </div>
              <div class="info-row">
                <strong style="color: #64748b;">Position</strong>
                <span style="font-weight: 600; color: #0f172a;">{position_title}</span>
              </div>
              <div class="info-row">
                <strong style="color: #64748b;">Company</strong>
                <span style="font-weight: 600; color: #0f172a;">{company_name or 'HireHand AI'}</span>
              </div>
            </div>

            {f'<div class="message-box">{message_body}</div>' if message_body else ''}

            <div style="text-align: center;">
              <span class="sender-pill">Sent securely by {sender_name} ({sender_email})</span>
            </div>
          </div>
          <div class="footer">
            <p style="margin: 0;">This report is strictly confidential and intended only for the recipient.</p>
            <p style="margin: 8px 0 0 0;">Powered by <strong>HireHand AI Analytics</strong></p>
          </div>
        </div>
      </body>
    </html>
    """

    payload = {
        "from": REPORTS_FROM_EMAIL,
        "to": to_email,
        "subject": subject or f"Confidential: Interview Report - {candidate_name} ({position_title})",
        "html": html_content,
        "attachments": [
            {
                "filename": f"Interview_Report_{candidate_name.replace(' ', '_')}.pdf",
                "content": pdf_base64
            }
        ]
    }

    try:
        r = resend.Emails.send(payload)
        print(f'✅ Resend: Report email with PDF sent to {to_email}')
        return r
    except Exception as e:
        print(f'❌ Resend: Failed to send report email: {e}')
        raise e
