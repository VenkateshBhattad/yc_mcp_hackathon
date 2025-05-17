#!/usr/bin/env python3
"""
Email Test Script with Config File

This script tests the email sending functionality by sending a test email
with the contents of a file and a dummy STL attachment, using settings from config.json.
"""

import os
import sys
import json
import argparse
from email_sender import EmailConfig, send_file_content_email

def load_config(config_path='config.json'):
    """Load email configuration from JSON file."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('email', {})
    except Exception as e:
        print(f"Error loading config file: {e}")
        return {}

def main():
    """Main function to test email sending."""
    parser = argparse.ArgumentParser(description='Email Test Script with Config File')
    parser.add_argument('--file', '-f', help='File whose contents to send', required=True)
    parser.add_argument('--to', '-t', help='Recipient email address', required=True)
    parser.add_argument('--subject', '-s', help='Email subject', default='Test Email from MCP')
    parser.add_argument('--cc', '-c', help='CC recipients (comma-separated)', default='')
    parser.add_argument('--config', help='Path to config file', default='config.json')
    parser.add_argument('--no-stl', action='store_true', help='Don\'t include dummy STL')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        return 1
    
    # Load configuration
    config = load_config(args.config)
    if not config:
        print("Error: Failed to load email configuration from config file")
        return 1
    
    # Split CC emails if provided
    cc_emails = [email.strip() for email in args.cc.split(',')] if args.cc else []
    
    # Create email configuration from config file
    email_config = EmailConfig(
        smtp_server=config.get('smtp_server'),
        smtp_port=config.get('smtp_port'),
        smtp_user=config.get('smtp_user'),
        smtp_password=config.get('smtp_password'),
        sender_email=config.get('sender_email'),
        use_tls=config.get('use_tls', True)
    )
    
    # Validate email configuration
    missing_fields = []
    for field in ['smtp_server', 'smtp_user', 'smtp_password']:
        if not getattr(email_config, field):
            missing_fields.append(field)
    
    if missing_fields:
        print(f"Error: Missing required fields in config: {', '.join(missing_fields)}")
        print("Please update your config.json file with these values.")
        return 1
    
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
        print("Failed to send email. Check SMTP settings in config file.")
        return 1

if __name__ == "__main__":
    sys.exit(main())