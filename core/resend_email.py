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
          body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #1e293b; }}
          .container {{ max-width: 640px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01); border: 1px solid #f1f5f9; }}
          .header {{ background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%); padding: 40px 30px; text-align: center; color: white; }}
          .header h1 {{ margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
          .header p {{ margin: 12px 0 0 0; font-size: 15px; opacity: 0.9; font-weight: 500; }}
          .content {{ padding: 40px 30px; }}
          .greeting {{ font-size: 18px; font-weight: 600; margin-top: 0; margin-bottom: 8px; color: #0f172a; }}
          .intro {{ font-size: 16px; margin-bottom: 30px; color: #475569; line-height: 1.6; }}
          
          .grid-card {{ background-color: #f8fafc; border-radius: 12px; padding: 24px; margin-bottom: 30px; border: 1px solid #e2e8f0; }}
          .grid-row {{ display: flex; justify-content: space-between; border-bottom: 1px dashed #cbd5e1; padding-bottom: 12px; margin-bottom: 12px; font-size: 15px; }}
          .grid-row:last-child {{ border-bottom: none; padding-bottom: 0; margin-bottom: 0; }}
          .grid-label {{ color: #64748b; font-weight: 500; }}
          .grid-value {{ font-weight: 700; color: #0f172a; text-align: right; }}
          
          .message-box {{ background: linear-gradient(to right, #fef8eb, #fffbeb); border-left: 4px solid #f59e0b; padding: 20px 24px; border-radius: 4px 12px 12px 4px; margin-bottom: 30px; font-size: 15px; line-height: 1.6; color: #92400e; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05); white-space: pre-wrap; }}
          
          .cta-area {{ text-align: center; margin-top: 40px; margin-bottom: 20px; }}
          .cta-text {{ font-size: 14px; color: #64748b; margin-bottom: 16px; font-weight: 500; }}
          
          .footer {{ background-color: #f1f5f9; padding: 30px; text-align: center; font-size: 13px; color: #64748b; border-top: 1px solid #e2e8f0; }}
          .sender-pill {{ display: inline-flex; align-items: center; justify-content: center; background-color: #e0e7ff; color: #4338ca; padding: 8px 16px; border-radius: 20px; font-size: 13px; font-weight: 600; box-shadow: 0 1px 2px 0 rgba(67, 56, 202, 0.1); }}
          .brand-text {{ margin-top: 16px; font-weight: 600; color: #3b82f6; }}
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>Interview Intelligence</h1>
            <p>Comprehensive AI-Generated Evaluation</p>
          </div>
          <div class="content">
            <h2 class="greeting">Hi there,</h2>
            <p class="intro">Please find attached the detailed <strong>HireHand AI</strong> interview assessment report for candidate <strong>{candidate_name}</strong>.</p>
            
            <div class="grid-card">
              <div class="grid-row">
                <span class="grid-label">Candidate Name</span>
                <span class="grid-value">{candidate_name}</span>
              </div>
              <div class="grid-row">
                <span class="grid-label">Target Position</span>
                <span class="grid-value">{position_title}</span>
              </div>
              <div class="grid-row">
                <span class="grid-label">Organization</span>
                <span class="grid-value">{company_name or 'HireHand AI Workspace'}</span>
              </div>
              <div class="grid-row">
                <span class="grid-label">Document Type</span>
                <span class="grid-value" style="color: #4f46e5;">PDF Report (Attached)</span>
              </div>
            </div>

            {f'<div class="message-box"><strong>Note from Recruiter:</strong><br/><br/>{message_body}</div>' if message_body else ''}

            <div class="cta-area">
              <div class="cta-text">This report contains sensitive candidate evaluation data.</div>
              <span class="sender-pill">Sent securely on behalf of {sender_name} ({sender_email})</span>
            </div>
          </div>
          <div class="footer">
            <p style="margin: 0; line-height: 1.5;">CONFIDENTIALITY NOTICE: This report and its attachments are confidential and intended solely for authorized personnel.</p>
            <div class="brand-text">Powered by HireHand AI Assessment Engine</div>
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


def send_team_invite_email(to_email: str, member_name: str, inviter_name: str, company_name: str, role: str, temp_password: str):
    """Send a team invitation email with temporary credentials."""
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent Team Invite to {to_email}")
        return

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080").rstrip("/")
    login_url = f"{frontend_url}/login"

    role_label = role.capitalize()

    html_content = f"""
    <html>
      <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #1a1a2e; background-color: #f8f9fc; margin: 0; padding: 20px;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08);">
          <div style="background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); padding: 32px 24px; text-align: center;">
            <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700;">Welcome to {company_name}</h1>
            <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0 0; font-size: 14px;">You've been invited to join the team on HireHand AI</p>
          </div>
          <div style="padding: 32px 24px;">
            <p>Hi <strong>{member_name}</strong>,</p>
            <p><strong>{inviter_name}</strong> has invited you to join <strong>{company_name}</strong> as a <strong style="color: #4F46E5;">{role_label}</strong> on HireHand AI.</p>
            <div style="background: #f0f0ff; padding: 20px; border-radius: 8px; margin: 24px 0; border-left: 4px solid #4F46E5;">
              <p style="margin: 0 0 8px 0; font-size: 13px; color: #666;">Your temporary login credentials:</p>
              <p style="margin: 0 0 4px 0;"><strong>Email:</strong> {to_email}</p>
              <p style="margin: 0;"><strong>Password:</strong> <code style="background: #e8e8f0; padding: 2px 8px; border-radius: 4px; font-size: 14px;">{temp_password}</code></p>
            </div>
            <p style="font-size: 13px; color: #e74c3c;">⚠️ Please change your password after your first login.</p>
            <div style="text-align: center; margin: 28px 0;">
              <a href="{login_url}" style="background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); color: #fff; padding: 14px 36px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">Login to HireHand</a>
            </div>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
            <p style="font-size: 12px; color: #999; text-align: center;">This is an automated email from HireHand AI. If you didn't expect this invitation, please ignore this email.</p>
          </div>
        </div>
      </body>
    </html>
    """

    try:
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": f"You're invited to join {company_name} on HireHand AI",
            "html": html_content
        })
        print(f"✅ Resend: Team invite email sent to {to_email}")
    except Exception as e:
        print(f"❌ Resend: Failed to send team invite email: {e}")


def send_ai_interview_email(
    to_email: str,
    candidate_name: str,
    position_title: str,
    company_name: str,
    interview_url: str,
    interview_type: str = "hybrid",
    time_limit: int = 20,
    max_questions: int = 10,
    expiry_display: str = "7 days",
    scheduled_display: str = "",
    hr_notes: str = "",
):
    """
    Send an AI Interview invitation email to the candidate.
    Includes: schedule info, interview rules, link expiry, and HR notes.
    """
    if not RESEND_API_KEY:
        print(f"⚠️ [WARNING] RESEND_API_KEY not found. Fake-sent AI Interview Email to {to_email}")
        print(f"   Link: {interview_url}")
        return

    company_display = company_name if company_name else "our team"

    # Build schedule row
    schedule_html = ""
    if scheduled_display:
        schedule_html = f"""
                <tr>
                  <td style="padding: 4px 0; color: #666;">Scheduled For:</td>
                  <td style="padding: 4px 0; font-weight: 600; color: #4f46e5;">{scheduled_display}</td>
                </tr>"""

    # Build HR notes section
    hr_notes_html = ""
    if hr_notes:
        hr_notes_html = f"""
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #22c55e; border-radius: 4px 8px 8px 4px; padding: 16px; margin: 20px 0;">
              <p style="margin: 0 0 8px 0; font-size: 14px; font-weight: 600; color: #166534;">📝 Note from the Hiring Team</p>
              <p style="margin: 0; font-size: 14px; color: #15803d; line-height: 1.6; white-space: pre-wrap;">{hr_notes}</p>
            </div>"""

    html_content = f"""
    <html>
      <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 30px auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">

          <!-- Header -->
          <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%); padding: 30px 30px; text-align: center;">
            <div style="font-size: 36px; margin-bottom: 8px;">🤖</div>
            <h1 style="color: #fff; margin: 0; font-size: 22px; font-weight: 600;">AI Interview Invitation</h1>
            <p style="color: rgba(255,255,255,0.85); margin: 6px 0 0 0; font-size: 14px;">{position_title}</p>
          </div>

          <!-- Body -->
          <div style="padding: 30px;">
            <p style="font-size: 16px;">Dear <strong>{candidate_name}</strong>,</p>

            <p>We're excited to invite you to an <strong>AI-powered interview</strong> for the <strong>{position_title}</strong> position at <strong>{company_display}</strong>.</p>

            <!-- Interview Details Card -->
            <div style="background: #f8f9ff; border: 1px solid #e0e7ff; border-radius: 10px; padding: 20px; margin: 20px 0;">
              <p style="margin: 0 0 10px 0; font-size: 14px; color: #6366f1; font-weight: 600;">📋 Interview Details</p>
              <table style="width: 100%; font-size: 14px;">
                <tr>
                  <td style="padding: 4px 0; color: #666; width: 140px;">Format:</td>
                  <td style="padding: 4px 0; font-weight: 500;">AI Voice Interview ({interview_type.replace('_', ' ').title()})</td>
                </tr>{schedule_html}
                <tr>
                  <td style="padding: 4px 0; color: #666;">Duration:</td>
                  <td style="padding: 4px 0; font-weight: 500;">~{time_limit} minutes</td>
                </tr>
                <tr>
                  <td style="padding: 4px 0; color: #666;">Questions:</td>
                  <td style="padding: 4px 0; font-weight: 500;">Up to {max_questions} questions</td>
                </tr>
                <tr>
                  <td style="padding: 4px 0; color: #666;">Link Valid For:</td>
                  <td style="padding: 4px 0; font-weight: 500; color: #dc2626;">{expiry_display}</td>
                </tr>
              </table>
            </div>

            <!-- CTA Button -->
            <div style="text-align: center; margin: 25px 0;">
              <a href="{interview_url}"
                 style="display: inline-block; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; text-decoration: none; padding: 14px 36px; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(99,102,241,0.35);">
                Start Your Interview →
              </a>
            </div>

            {hr_notes_html}

            <!-- Interview Rules -->
            <div style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 16px; margin: 20px 0;">
              <p style="margin: 0 0 10px 0; font-size: 14px; font-weight: 600; color: #92400e;">⚠️ Important Interview Rules</p>
              <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #78350f; line-height: 1.8;">
                <li><strong>Camera must be ON</strong> throughout the interview — your face will be monitored</li>
                <li><strong>5 seconds of silence</strong> will cause the AI to move to the next question automatically</li>
                <li><strong>Tab switching is tracked</strong> — switching tabs or windows will be recorded and flagged</li>
                <li>Speak <strong>clearly and naturally</strong> — the AI transcribes your voice in real-time</li>
                <li>You can take your time to think, but avoid long pauses beyond 5 seconds</li>
                <li>Ensure a <strong>quiet environment</strong> with minimal background noise</li>
                <li>Use a <strong>stable internet connection</strong> (WiFi recommended over mobile data)</li>
                <li>Use <strong>Google Chrome or Microsoft Edge</strong> for the best experience</li>
                <li>Allow <strong>microphone and camera access</strong> when prompted by the browser</li>
              </ul>
            </div>

            <!-- Tips Section -->
            <div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 16px; margin: 20px 0;">
              <p style="margin: 0 0 8px 0; font-size: 14px; font-weight: 600; color: #0c4a6e;">💡 Tips for a Great Interview</p>
              <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #075985; line-height: 1.8;">
                <li>Practice speaking your answers out loud before starting</li>
                <li>Structure your answers using the STAR method (Situation, Task, Action, Result)</li>
                <li>Be specific — mention technologies, projects, and measurable outcomes</li>
                <li>It's okay to ask the AI to repeat a question if you didn't hear it clearly</li>
              </ul>
            </div>

            <p style="font-size: 14px; color: #666; margin-top: 25px;">
              This interview is conducted by HireHand AI. Your responses will be recorded and evaluated by our intelligent assessment engine. The hiring team will review your results.
            </p>

            <p style="font-size: 14px; color: #666;">Best of luck for your interview! 🍀</p>
            <p style="font-size: 14px; color: #888;">— The {company_display} Hiring Team via HireHand AI</p>
          </div>

          <!-- Footer -->
          <div style="background: #f9fafb; padding: 15px 30px; text-align: center; border-top: 1px solid #f0f0f0;">
            <p style="margin: 0; font-size: 11px; color: #aaa;">Powered by HireHand AI • This is an automated invitation</p>
          </div>
        </div>
      </body>
    </html>
    """

    try:
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": f"🤖 AI Interview Invitation: {position_title}",
            "html": html_content,
        })
        print(f"✅ Resend: AI Interview email sent to {to_email}")
    except Exception as e:
        print(f"❌ Resend: Failed to send AI interview email: {e}")

