#!/usr/bin/env python3
"""
Email Test Script

This script tests the email sending functionality by sending a test email
with the contents of a file and a dummy STL attachment.
"""

import os
import sys
import argparse
from email_sender import EmailConfig, send_file_content_email

def main():
    """Main function to test email sending."""
    parser = argparse.ArgumentParser(description='Email Test Script')
    parser.add_argument('--file', '-f', help='File whose contents to send', required=True)
    parser.add_argument('--to', '-t', help='Recipient email address', required=True)
    parser.add_argument('--subject', '-s', help='Email subject', default='Test Email from MCP')
    parser.add_argument('--cc', '-c', help='CC recipients (comma-separated)', default='')
    parser.add_argument('--server', help='SMTP server', default=os.environ.get('SMTP_SERVER'))
    parser.add_argument('--port', help='SMTP port', type=int, default=int(os.environ.get('SMTP_PORT', '587')))
    parser.add_argument('--user', help='SMTP username', default=os.environ.get('SMTP_USER'))
    parser.add_argument('--password', help='SMTP password', default=os.environ.get('SMTP_PASSWORD'))
    parser.add_argument('--sender', help='Sender email', default=os.environ.get('SENDER_EMAIL'))
    parser.add_argument('--no-stl', action='store_true', help='Don\'t include dummy STL')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        return 1
    
    # Split CC emails if provided
    cc_emails = [email.strip() for email in args.cc.split(',')] if args.cc else []
    
    # Check SMTP configuration
    required_settings = ['server', 'port', 'user', 'password']
    missing_settings = [setting for setting in required_settings if not getattr(args, setting)]
    
    if missing_settings:
        print(f"Error: Missing required SMTP settings: {', '.join(missing_settings)}")
        print("Please set them via command-line arguments or environment variables.")
        return 1
    
    # Create email configuration
    email_config = EmailConfig(
        smtp_server=args.server,
        smtp_port=args.port,
        smtp_user=args.user,
        smtp_password=args.password,
        sender_email=args.sender or args.user
    )
    
    print(f"Sending email to {args.to}")
    print(f"  with file: {args.file}")
    print(f"  SMTP server: {email_config.smtp_server}:{email_config.smtp_port}")
    print(f"  From: {email_config.sender_email}")
    
    # Send the email
    success = send_file_content_email(
        email_config,
        args.to,
        args.subject,
        args.file,
        cc_emails,
        not args.no_stl
    )
    
    if success:
        print("Email sent successfully!")
        return 0
    else:
        print("Failed to send email")
        return 1

if __name__ == "__main__":
    sys.exit(main())