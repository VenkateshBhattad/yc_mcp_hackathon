#!/usr/bin/env python3
"""
Google Drive API Test Script

This script demonstrates several Google Drive API operations:
1. Create a folder
2. Upload a file to that folder
3. Share the folder with an email
4. List files in the folder
"""

import os
import sys
import json
import argparse
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Gets authenticated Google Drive service."""
    # Paths for credentials and token
    current_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(os.path.dirname(current_dir), 'token.json')
    credentials_path = os.path.join(os.path.dirname(current_dir), 'credentials.json')
    
    creds = None
    
    # Load saved credentials if they exist
    if os.path.exists(token_path):
        try:
            token_data = json.loads(open(token_path).read())
            # Load credentials from token.json
            print(f"Loading credentials from {token_path}")
            
            # Get client info from credentials.json
            client_data = json.loads(open(credentials_path).read())
            client_id = client_data["installed"]["client_id"]
            client_secret = client_data["installed"]["client_secret"]
            
            # Create complete auth info
            token_info = {
                "token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": client_id,
                "client_secret": client_secret,
                "scopes": token_data.get("scope").split()
            }
            
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        except Exception as e:
            print(f"Error loading credentials: {e}")
            creds = None
    
    # If credentials don't exist or are invalid, refresh or get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing credentials...")
            creds.refresh(Request())
        else:
            print("No valid credentials found. Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            print(f"Saved refreshed credentials to {token_path}")
    
    # Create and return the service
    print("Creating Google Drive service...")
    return build('drive', 'v3', credentials=creds)


def create_folder(service, folder_name, parent_id=None):
    """Create a folder in Google Drive."""
    print(f"Creating folder: {folder_name}")
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    
    if parent_id:
        file_metadata['parents'] = [parent_id]
        print(f"Parent folder ID: {parent_id}")
    
    folder = service.files().create(
        body=file_metadata,
        fields='id, name, webViewLink'
    ).execute()
    
    print(f"Folder created successfully!")
    print(f"Folder ID: {folder.get('id')}")
    print(f"Web link: {folder.get('webViewLink')}")
    
    return folder


def upload_file(service, file_path, folder_id=None):
    """Upload a file to Google Drive."""
    # Get file details
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    # Determine MIME type based on file extension
    ext = os.path.splitext(file_path)[1].lower()
    mime_type = "application/octet-stream"  # Default
    
    # Map common extensions to MIME types
    mime_map = {
        '.txt': 'text/plain',
        '.html': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }
    
    if ext in mime_map:
        mime_type = mime_map[ext]
    
    print(f"Uploading file: {file_name} ({mime_type})")
    print(f"File size: {file_size} bytes")
    
    if folder_id:
        print(f"Target folder ID: {folder_id}")
    
    # Prepare file metadata
    file_metadata = {
        'name': file_name,
        'description': 'Uploaded via Python test script'
    }
    
    if folder_id:
        file_metadata['parents'] = [folder_id]
    
    # Create media for upload
    media = MediaFileUpload(
        file_path,
        mimetype=mime_type,
        resumable=True
    )
    
    # Upload the file
    print("Uploading file to Google Drive...")
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink, mimeType, size'
    ).execute()
    
    # Print results
    print("Upload successful!")
    print(f"File ID: {file.get('id')}")
    print(f"File name: {file.get('name')}")
    print(f"Web link: {file.get('webViewLink')}")
    
    return file


def share_item(service, file_id, email, role='reader'):
    """Share a file or folder with a user."""
    print(f"Sharing item {file_id} with {email} as {role}")
    
    # Get item details
    item = service.files().get(
        fileId=file_id,
        fields='name, mimeType'
    ).execute()
    
    item_type = "Folder" if item.get('mimeType') == 'application/vnd.google-apps.folder' else "File"
    print(f"Sharing {item_type}: {item.get('name')}")
    
    # Create the permission
    user_permission = {
        'type': 'user',
        'role': role,
        'emailAddress': email
    }
    
    # Add the permission
    permission = service.permissions().create(
        fileId=file_id,
        body=user_permission,
        fields='id, emailAddress, role'
    ).execute()
    
    print(f"Successfully shared with {permission.get('emailAddress')} as {permission.get('role')}")
    print(f"Permission ID: {permission.get('id')}")
    
    return permission


def list_files(service, folder_id=None):
    """List files in a folder."""
    if folder_id:
        print(f"Listing files in folder: {folder_id}")
        query = f"'{folder_id}' in parents"
    else:
        print("Listing all files")
        query = None
    
    # Get files
    results = service.files().list(
        q=query,
        pageSize=50,
        fields="files(id, name, mimeType, createdTime, modifiedTime, size, webViewLink)"
    ).execute()
    
    items = results.get('files', [])
    
    if not items:
        print("No files found.")
    else:
        print(f"Found {len(items)} files:")
        for item in items:
            item_type = "Folder" if item.get('mimeType') == 'application/vnd.google-apps.folder' else "File"
            print(f"  - {item_type}: {item.get('name')} (ID: {item.get('id')})")
            if item.get('webViewLink'):
                print(f"    Link: {item.get('webViewLink')}")
    
    return items


def main():
    """Main function to test Google Drive API operations."""
    parser = argparse.ArgumentParser(description='Google Drive API Test Script')
    parser.add_argument('--file', '-f', help='File to upload')
    parser.add_argument('--email', '-e', help='Email to share with')
    parser.add_argument('--operation', '-o', choices=['create-folder', 'upload', 'share', 'list', 'all'], 
                        default='all', help='Operation to perform')
    
    args = parser.parse_args()
    
    # Default to test4.txt if no file is specified
    file_path = args.file
    if not file_path and (args.operation in ['upload', 'all']):
        file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                              'mcp_test', 'test4', 'test4.txt')
        if not os.path.exists(file_path):
            print(f"Default test file not found: {file_path}")
            return
    
    # Email to share with (optional)
    share_email = args.email
    
    try:
        # Get authenticated service
        service = get_drive_service()
        
        # Create a test folder
        folder_name = "MCP Test Folder " + os.path.basename(__file__)
        folder = None
        file = None
        
        if args.operation in ['create-folder', 'all']:
            folder = create_folder(service, folder_name)
            print("\n" + "-"*50 + "\n")
        
        # Upload the file to the folder
        if args.operation in ['upload', 'all'] and file_path:
            file = upload_file(service, file_path, folder.get('id') if folder else None)
            print("\n" + "-"*50 + "\n")
        
        # Share the folder if email is provided
        if args.operation in ['share', 'all'] and share_email:
            if folder:
                share_item(service, folder.get('id'), share_email, 'writer')
                print("\n" + "-"*50 + "\n")
        
        # List files in the folder
        if args.operation in ['list', 'all'] and folder:
            list_files(service, folder.get('id'))
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()