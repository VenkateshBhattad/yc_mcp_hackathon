#!/usr/bin/env python3
"""
Email Sender Module for MCP

This module provides functionality to send emails with file contents
and attachments using SMTP.
"""

import os
import json
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate
from typing import List, Optional, Dict, Union

logger = logging.getLogger(__name__)

def load_config_from_file(config_path: str = 'config.json') -> Dict:
    """Load email configuration from a JSON file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Dict containing email configuration or empty dict if file not found
    """
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('email', {})
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        return {}


class EmailConfig:
    """Email configuration settings."""
    
    def __init__(
        self,
        smtp_server: str = None,
        smtp_port: int = None,
        smtp_user: str = None,
        smtp_password: str = None,
        use_tls: bool = True,
        sender_email: str = None,
        config_file: str = None
    ):
        # First try to load from config file if provided
        config = {}
        if config_file:
            config = load_config_from_file(config_file)
        
        # Use values in this order of precedence: 
        # 1. Directly provided parameters
        # 2. Values from config file
        # 3. Environment variables
        self.smtp_server = smtp_server or config.get('smtp_server') or os.environ.get("SMTP_SERVER")
        self.smtp_port = smtp_port or config.get('smtp_port') or int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or config.get('smtp_user') or os.environ.get("SMTP_USER")
        self.smtp_password = smtp_password or config.get('smtp_password') or os.environ.get("SMTP_PASSWORD")
        self.use_tls = use_tls if use_tls is not None else config.get('use_tls', True) if 'use_tls' in config else (os.environ.get("SMTP_USE_TLS", "true").lower() == "true")
        self.sender_email = sender_email or config.get('sender_email') or os.environ.get("SENDER_EMAIL") or self.smtp_user
    
    @classmethod
    def from_config_file(cls, config_file: str = 'config.json') -> 'EmailConfig':
        """Create an EmailConfig instance from a config file.
        
        Args:
            config_file: Path to the configuration file
            
        Returns:
            EmailConfig instance with settings from the config file
        """
        return cls(config_file=config_file)


class EmailSender:
    """Class to handle email sending functionality."""
    
    def __init__(self, config: EmailConfig):
        self.config = config
    
    def _create_message(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachments: Optional[List[Dict[str, str]]] = None,
        cc_emails: Optional[List[str]] = None,
    ) -> MIMEMultipart:
        """Create an email message with optional attachments.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body text
            attachments: List of dicts with keys 'file_path', 'filename', 'content_type'
            cc_emails: List of CC recipient email addresses
            
        Returns:
            MIMEMultipart message object
        """
        # Create message container
        msg = MIMEMultipart()
        msg['From'] = self.config.sender_email
        msg['To'] = to_email
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = subject
        
        # Add CC recipients if provided
        if cc_emails:
            msg['Cc'] = ", ".join(cc_emails)
        
        # Attach the message body
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach files if provided
        if attachments:
            for attachment in attachments:
                self._attach_file(msg, attachment)
        
        return msg
    
    def _attach_file(self, msg: MIMEMultipart, attachment: Dict[str, str]) -> None:
        """Attach a file to the email message.
        
        Args:
            msg: Email message to attach file to
            attachment: Dict with keys 'file_path', 'filename', 'content_type'
        """
        file_path = attachment.get('file_path')
        filename = attachment.get('filename')
        content_type = attachment.get('content_type', 'application/octet-stream')
        
        # Read file content
        try:
            with open(file_path, 'rb') as f:
                attachment_data = f.read()
            
            part = MIMEApplication(attachment_data, Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            part['Content-Type'] = content_type
            
            msg.attach(part)
            logger.info(f"Attached file: {filename}")
        except Exception as e:
            logger.error(f"Failed to attach file {file_path}: {e}")
            raise
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachments: Optional[List[Dict[str, str]]] = None,
        cc_emails: Optional[List[str]] = None,
    ) -> bool:
        """Send an email with optional attachments.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body text
            attachments: List of dicts with keys 'file_path', 'filename', 'content_type'
            cc_emails: List of CC recipient email addresses
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        # Validate email configuration
        if not all([
            self.config.smtp_server,
            self.config.smtp_port,
            self.config.smtp_user,
            self.config.smtp_password,
            self.config.sender_email
        ]):
            logger.error("Email configuration is incomplete. Check SMTP settings.")
            return False
        
        # Create email message
        msg = self._create_message(to_email, subject, body, attachments, cc_emails)
        
        # Determine recipients list (To + CC)
        recipients = [to_email]
        if cc_emails:
            recipients.extend(cc_emails)
        
        # Send the email
        try:
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls()
                
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.sendmail(self.config.sender_email, recipients, msg.as_string())
                
                logger.info(f"Email sent successfully to {to_email}")
                return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


def send_file_content_email(
    config: Union[EmailConfig, str],
    to_email: str,
    subject: str,
    file_path: str,
    cc_emails: Optional[List[str]] = None,
    include_dummy_stl: bool = True
) -> bool:
    """Send an email with the contents of a file and an optional dummy STL attachment.
    
    Args:
        config: Either an EmailConfig object or a path to a config file
        to_email: Recipient email address
        subject: Email subject
        file_path: Path to the file whose contents will be included in the email
        cc_emails: List of CC recipient email addresses
        include_dummy_stl: Whether to include a dummy STL attachment
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    """Send an email with the contents of a file and an optional dummy STL attachment.
    
    Args:
        config: Email configuration
        to_email: Recipient email address
        subject: Email subject
        file_path: Path to the file whose contents will be included in the email
        cc_emails: List of CC recipient email addresses
        include_dummy_stl: Whether to include a dummy STL attachment
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Convert string config path to EmailConfig object if needed
        if isinstance(config, str):
            email_config = EmailConfig.from_config_file(config)
        else:
            email_config = config
        
        # Read the file content
        with open(file_path, 'r') as f:
            file_content = f.read()
        
        # Create email body
        body = f"File: {os.path.basename(file_path)}\n\n"
        body += "=============== FILE CONTENTS ===============\n\n"
        body += file_content
        body += "\n\n============================================\n"
        body += "\nThis email was sent via the MCP Google Drive server."
        
        # Prepare attachments
        attachments = []
        
        # Include the original file as an attachment
        attachments.append({
            'file_path': file_path,
            'filename': os.path.basename(file_path),
            'content_type': 'text/plain',
        })
        
        # Include dummy STL if requested
        if include_dummy_stl:
            dummy_stl_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'mcp_test',
                'dummy.stl'
            )
            
            if os.path.exists(dummy_stl_path):
                attachments.append({
                    'file_path': dummy_stl_path,
                    'filename': 'dummy.stl',
                    'content_type': 'model/stl',
                })
        
        # Send the email
        sender = EmailSender(email_config)
        return sender.send_email(to_email, subject, body, attachments, cc_emails)
    
    except Exception as e:
        logger.error(f"Failed to send file content email: {e}")
        return False