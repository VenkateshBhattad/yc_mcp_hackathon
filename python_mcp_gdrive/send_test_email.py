#!/usr/bin/env python3
"""
Send Test Email Script

This script sends a test email to the specified address with the contents
of test4.txt and a dummy STL attachment using settings from config.json.
"""

import os
import sys
from email_sender import send_file_content_email

def main():
    """Send a test email with test4.txt contents."""
    # File path for test4.txt
    file_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'mcp_test',
        'test4',
        'test4.txt'
    )
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return 1
    
    # Recipient email
    to_email = "venkatesh.bhattad@gmail.com"
    
    # Email subject
    subject = "test from MCP"
    
    # Send the email using config.json
    print(f"Sending email to {to_email}")
    print(f"  with file: {file_path}")
    print(f"  subject: {subject}")
    print(f"  config: config.json")
    
    # Send the email (passing config file path as string)
    success = send_file_content_email(
        "config.json",
        to_email,
        subject,
        file_path,
        cc_emails=None,
        include_dummy_stl=True
    )
    
    if success:
        print("Email sent successfully!")
        return 0
    else:
        print("Failed to send email. Check your config.json settings.")
        return 1

if __name__ == "__main__":
    sys.exit(main())