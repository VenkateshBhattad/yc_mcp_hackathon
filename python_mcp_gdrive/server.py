#!/usr/bin/env python3
"""
Google Drive and Docs MCP Server

This MCP server allows you to connect to Google Drive and Google Docs through Claude.
"""

import os
import json
import base64
import io
import tempfile
import logging
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urljoin

import mcp
from mcp.server import McpServer, McpStdio, ResourceTemplate
from pydantic import BaseModel, Field

# Import email functionality
from email_sender import EmailConfig, send_file_content_email
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/documents', 
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.readonly'
]

# Path to the credentials file
CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'credentials.json')
TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'token.json')

# Email configuration (load from config file or environment variables)
EMAIL_CONFIG = EmailConfig.from_config_file('config.json')


# Helper function to make a temporary file
def get_temp_file(prefix='mcp-gdrive-'):
    """Create a temporary file with a given prefix."""
    fd, path = tempfile.mkstemp(prefix=prefix)
    os.close(fd)
    return path


# Authentication and API client setup
def get_drive_service():
    """Gets authenticated Google Drive service."""
    creds = None
    
    # Load saved credentials if they exist
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_info(
            json.loads(open(TOKEN_PATH).read()),
            SCOPES
        )
    
    # If credentials don't exist or are invalid, refresh or get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    
    return build('drive', 'v3', credentials=creds)


def get_docs_service():
    """Gets authenticated Google Docs service."""
    creds = None
    
    # Load saved credentials if they exist
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_info(
            json.loads(open(TOKEN_PATH).read()),
            SCOPES
        )
    
    # If credentials don't exist or are invalid, refresh or get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    
    return build('docs', 'v1', credentials=creds)


# Initialize Google API services
drive_service = None
docs_service = None


def init_services():
    """Initialize Google API services."""
    global drive_service, docs_service
    try:
        logger.info("Initializing Google API services...")
        drive_service = get_drive_service()
        docs_service = get_docs_service()
        logger.info("Google API services initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Google API services: {e}")
        return False


# Model definitions for API requests
class CreateFolderInput(BaseModel):
    name: str = Field(..., description="The name of the new folder")
    parent_id: Optional[str] = Field(None, description="Optional parent folder ID. If not provided, creates folder in the root")


class ListFoldersInput(BaseModel):
    parent_id: Optional[str] = Field(None, description="Optional parent folder ID. If not provided, lists folders in the root of My Drive")


class UploadFileBase64Input(BaseModel):
    name: str = Field(..., description="Filename to use when saving to Drive")
    mime_type: str = Field(..., description="The MIME type of the file")
    base64_content: str = Field(..., description="Base64 encoded content of the file")
    folder_id: Optional[str] = Field(None, description="Optional folder ID to upload the file to")
    description: Optional[str] = Field(None, description="Optional file description")


class UploadFileFromUrlInput(BaseModel):
    name: str = Field(..., description="Filename to use when saving to Drive")
    mime_type: str = Field(..., description="The MIME type of the file")
    url: str = Field(..., description="URL of the file to download and upload")
    folder_id: Optional[str] = Field(None, description="Optional folder ID to upload the file to")
    description: Optional[str] = Field(None, description="Optional file description")


class CopyFileInput(BaseModel):
    file_id: str = Field(..., description="ID of the file to copy")
    new_name: Optional[str] = Field(None, description="Optional new name for the copied file")
    destination_folder_id: Optional[str] = Field(None, description="Optional destination folder ID")


class DownloadFileBase64Input(BaseModel):
    file_id: str = Field(..., description="The ID of the file to download from Google Drive")


class ShareDriveItemInput(BaseModel):
    file_id: str = Field(..., description="The ID of the file or folder to share")
    email_address: str = Field(..., description="The email address of the user to share with")
    role: str = Field(..., description="The role to grant to the user", enum=["reader", "commenter", "writer", "owner"])
    send_notification_email: Optional[bool] = Field(True, description="Whether to send a notification email to the user")
    message: Optional[str] = Field("", description="Optional message to include in the notification email")


class ListPermissionsInput(BaseModel):
    file_id: str = Field(..., description="The ID of the file or folder to check permissions for")


class CreateDocInput(BaseModel):
    title: str = Field(..., description="The title of the new document")
    content: Optional[str] = Field("", description="Optional initial content for the document")


class UpdateDocInput(BaseModel):
    doc_id: str = Field(..., description="The ID of the document to update")
    content: str = Field(..., description="The content to add to the document")
    replace_all: Optional[bool] = Field(False, description="Whether to replace all content (true) or append (false)")


class SearchDocsInput(BaseModel):
    query: str = Field(..., description="The search query to find documents")


class DeleteDocInput(BaseModel):
    doc_id: str = Field(..., description="The ID of the document to delete")


class ExportDocInput(BaseModel):
    doc_id: str = Field(..., description="The ID of the Google Doc to export")
    format: str = Field(..., description="The format to export to", enum=["pdf", "docx", "txt", "html", "odt", "rtf", "epub"])


class UploadBatchInput(BaseModel):
    class FileItem(BaseModel):
        name: str = Field(..., description="Filename to use when saving to Drive")
        mime_type: str = Field(..., description="The MIME type of the file")
        base64_content: str = Field(..., description="Base64 encoded content of the file")
    
    files: List[FileItem] = Field(..., description="Array of files to upload")
    folder_id: Optional[str] = Field(None, description="Optional folder ID to upload all files to")


class CreateDocTemplateInput(BaseModel):
    title: str = Field(..., description="The title for the new document")
    subject: str = Field(..., description="The subject/topic the document should be about")
    style: str = Field(..., description="The writing style (e.g., formal, casual, academic)")


class AnalyzeDocInput(BaseModel):
    doc_id: str = Field(..., description="The ID of the document to analyze")


class CreateFolderStructureInput(BaseModel):
    project_name: str = Field(..., description="The name of the main project folder")
    project_type: str = Field(..., description="The type of project (e.g., research, marketing, software development)")


class SendFileContentEmailInput(BaseModel):
    file_path: str = Field(..., description="Path to the file whose contents will be included in the email")
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    cc_emails: Optional[List[str]] = Field(None, description="Optional list of CC recipient email addresses")
    smtp_server: Optional[str] = Field(None, description="SMTP server (or use environment variable)")
    smtp_port: Optional[int] = Field(None, description="SMTP port (or use environment variable)")
    smtp_user: Optional[str] = Field(None, description="SMTP username (or use environment variable)")
    smtp_password: Optional[str] = Field(None, description="SMTP password (or use environment variable)")
    sender_email: Optional[str] = Field(None, description="Sender email address (or use environment variable)")
    include_dummy_stl: Optional[bool] = Field(True, description="Whether to include a dummy STL attachment")


# MCP Server implementation
class GoogleDriveMcpServer:
    def __init__(self):
        self.server = McpServer(name="google-drive", version="1.0.0")
        self.register_resources()
        self.register_tools()
        self.register_prompts()
    
    def register_resources(self):
        """Register MCP resources."""
        # List all Google Docs
        @self.server.resource("list-docs", "googledocs://list")
        async def list_docs(uri):
            try:
                response = drive_service.files().list(
                    q="mimeType='application/vnd.google-apps.document'",
                    fields="files(id, name, createdTime, modifiedTime)",
                    pageSize=50
                ).execute()
                
                files = response.get('files', [])
                content = "Google Docs in your Drive:\n\n"
                
                if not files:
                    content += "No Google Docs found."
                else:
                    for file in files:
                        content += f"Title: {file.get('name')}\n"
                        content += f"ID: {file.get('id')}\n"
                        content += f"Created: {file.get('createdTime')}\n"
                        content += f"Last Modified: {file.get('modifiedTime')}\n\n"
                
                return {"contents": [{"uri": uri.href, "text": content}]}
            except Exception as e:
                logger.error(f"Error listing documents: {e}")
                return {"contents": [{"uri": uri.href, "text": f"Error listing documents: {e}"}]}
        
        # Get a specific document by ID
        @self.server.resource("get-doc", ResourceTemplate("googledocs://{doc_id}"))
        async def get_doc(uri, variables):
            try:
                doc_id = variables.get("doc_id")
                doc = docs_service.documents().get(documentId=doc_id).execute()
                
                # Extract the document content
                content = f"Document: {doc.get('title')}\n\n"
                
                # Process the document content from the complex data structure
                document = doc
                if document and document.get('body') and document.get('body').get('content'):
                    text_content = ""
                    
                    # Loop through the document's structural elements
                    for element in document['body']['content']:
                        if 'paragraph' in element:
                            for paragraph_element in element['paragraph']['elements']:
                                if 'textRun' in paragraph_element and 'content' in paragraph_element['textRun']:
                                    text_content += paragraph_element['textRun']['content']
                    
                    content += text_content
                
                return {"contents": [{"uri": uri.href, "text": content}]}
            except Exception as e:
                logger.error(f"Error getting document {variables.get('doc_id')}: {e}")
                return {"contents": [{"uri": uri.href, "text": f"Error getting document {variables.get('doc_id')}: {e}"}]}
        
        # List files in Google Drive
        @self.server.resource("list-drive-files", ResourceTemplate("googledrive://files{/folder_id}{?query,mimetype}"))
        async def list_drive_files(uri, variables):
            try:
                folder_id = variables.get("folder_id")
                query = variables.get("query")
                mimetype = variables.get("mimetype")
                
                # Build query string
                query_string = ''
                
                # Add folder constraint if provided
                if folder_id:
                    query_string += f"'{folder_id}' in parents"
                
                # Add mime type constraint if provided
                if mimetype:
                    if query_string:
                        query_string += ' and '
                    query_string += f"mimeType='{mimetype}'"
                
                # Add name search if provided
                if query:
                    if query_string:
                        query_string += ' and '
                    query_string += f"name contains '{query}'"
                
                # Fetch files
                response = drive_service.files().list(
                    q=query_string if query_string else None,
                    fields="files(id, name, mimeType, createdTime, modifiedTime, size, webViewLink, parents)",
                    pageSize=50
                ).execute()
                
                files = response.get('files', [])
                content = "Google Drive Files:\n\n"
                
                if not files:
                    content += "No files found."
                else:
                    for file in files:
                        content += f"Name: {file.get('name')}\n"
                        content += f"ID: {file.get('id')}\n"
                        content += f"Type: {file.get('mimeType')}\n"
                        
                        if file.get('size'):
                            size_in_kb = int(file.get('size')) / 1024
                            size_in_mb = size_in_kb / 1024
                            
                            if size_in_mb >= 1:
                                content += f"Size: {size_in_mb:.2f} MB\n"
                            else:
                                content += f"Size: {size_in_kb:.2f} KB\n"
                        
                        content += f"Created: {file.get('createdTime')}\n"
                        content += f"Modified: {file.get('modifiedTime')}\n"
                        
                        if file.get('webViewLink'):
                            content += f"Link: {file.get('webViewLink')}\n"
                        
                        content += "\n"
                
                return {"contents": [{"uri": uri.href, "text": content}]}
            except Exception as e:
                logger.error(f"Error listing files: {e}")
                return {"contents": [{"uri": uri.href, "text": f"Error listing files: {e}"}]}
        
        # Get file details
        @self.server.resource("get-drive-file", ResourceTemplate("googledrive://file/{file_id}"))
        async def get_drive_file(uri, variables):
            try:
                file_id = variables.get("file_id")
                
                # Get file metadata
                response = drive_service.files().get(
                    fileId=file_id,
                    fields="id, name, mimeType, createdTime, modifiedTime, size, description, webViewLink, iconLink, thumbnailLink, parents, shared, owners, lastModifyingUser"
                ).execute()
                
                file = response
                content = "File Details:\n\n"
                content += f"Name: {file.get('name')}\n"
                content += f"ID: {file.get('id')}\n"
                content += f"Type: {file.get('mimeType')}\n"
                
                if file.get('size'):
                    size_in_kb = int(file.get('size')) / 1024
                    size_in_mb = size_in_kb / 1024
                    
                    if size_in_mb >= 1:
                        content += f"Size: {size_in_mb:.2f} MB\n"
                    else:
                        content += f"Size: {size_in_kb:.2f} KB\n"
                
                if file.get('description'):
                    content += f"Description: {file.get('description')}\n"
                
                content += f"Created: {file.get('createdTime')}\n"
                content += f"Modified: {file.get('modifiedTime')}\n"
                
                if file.get('shared'):
                    content += "Shared: Yes\n"
                
                if file.get('owners') and len(file.get('owners', [])) > 0:
                    owner = file.get('owners')[0]
                    content += f"Owner: {owner.get('displayName')} ({owner.get('emailAddress')})\n"
                
                if file.get('lastModifyingUser'):
                    last_user = file.get('lastModifyingUser')
                    content += f"Last Modified By: {last_user.get('displayName')} ({last_user.get('emailAddress')})\n"
                
                if file.get('webViewLink'):
                    content += f"Web Link: {file.get('webViewLink')}\n"
                
                if file.get('thumbnailLink'):
                    content += "Thumbnail Available: Yes\n"
                
                # For Google Docs specifically, provide more context
                if file.get('mimeType') == 'application/vnd.google-apps.document':
                    content += f"\nThis is a Google Document. You can view its content using googledocs://{file.get('id')}\n"
                
                return {"contents": [{"uri": uri.href, "text": content}]}
            except Exception as e:
                logger.error(f"Error getting file {variables.get('file_id')}: {e}")
                return {"contents": [{"uri": uri.href, "text": f"Error getting file {variables.get('file_id')}: {e}"}]}
    
    def register_tools(self):
        """Register MCP tools."""
        # Create folder
        @self.server.tool("create-folder", CreateFolderInput)
        async def create_folder(input_data):
            try:
                # Set up file metadata
                file_metadata = {
                    'name': input_data.name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                if input_data.parent_id:
                    file_metadata['parents'] = [input_data.parent_id]
                
                # Create the folder
                response = drive_service.files().create(
                    body=file_metadata,
                    fields='id, name, webViewLink'
                ).execute()
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Folder created successfully!\nName: {response.get('name')}\nFolder ID: {response.get('id')}\nLink: {response.get('webViewLink')}"
                    }]
                }
            except Exception as e:
                logger.error(f"Error creating folder: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error creating folder: {e}"
                    }],
                    "isError": True
                }
        
        # List folders
        @self.server.tool("list-folders", ListFoldersInput)
        async def list_folders(input_data):
            try:
                query = "mimeType='application/vnd.google-apps.folder'"
                if input_data.parent_id:
                    query += f" and '{input_data.parent_id}' in parents"
                
                response = drive_service.files().list(
                    q=query,
                    fields="files(id, name, createdTime, modifiedTime)",
                    pageSize=50
                ).execute()
                
                folders = response.get('files', [])
                content = "Google Drive Folders:\n\n"
                
                if not folders:
                    content += "No folders found."
                else:
                    for folder in folders:
                        content += f"Name: {folder.get('name')}\n"
                        content += f"ID: {folder.get('id')}\n"
                        content += f"Created: {folder.get('createdTime')}\n"
                        content += f"Last Modified: {folder.get('modifiedTime')}\n\n"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": content
                    }]
                }
            except Exception as e:
                logger.error(f"Error listing folders: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error listing folders: {e}"
                    }],
                    "isError": True
                }
        
        # Upload file (base64)
        @self.server.tool("upload-file-base64", UploadFileBase64Input)
        async def upload_file_base64(input_data):
            try:
                # Decode the base64 content
                file_content = base64.b64decode(input_data.base64_content)
                
                # Create a temporary file
                temp_path = get_temp_file('upload-base64-')
                with open(temp_path, 'wb') as f:
                    f.write(file_content)
                
                # Set up file metadata
                file_metadata = {
                    'name': input_data.name
                }
                
                if input_data.description:
                    file_metadata['description'] = input_data.description
                
                if input_data.folder_id:
                    file_metadata['parents'] = [input_data.folder_id]
                
                # Upload the file
                media = MediaFileUpload(
                    temp_path,
                    mimetype=input_data.mime_type,
                    resumable=True
                )
                
                response = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink, mimeType, size'
                ).execute()
                
                # Clean up the temporary file
                os.unlink(temp_path)
                
                # Format size information
                size_str = f"{response.get('size', 'unknown')} bytes"
                if response.get('size'):
                    size_bytes = int(response.get('size'))
                    if size_bytes > 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
                    elif size_bytes > 1024:
                        size_str = f"{size_bytes / 1024:.2f} KB"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"File uploaded successfully!\nName: {response.get('name')}\nFile ID: {response.get('id')}\nType: {response.get('mimeType')}\nSize: {size_str}\nLink: {response.get('webViewLink')}"
                    }]
                }
            except Exception as e:
                logger.error(f"Error uploading file: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error uploading file: {e}"
                    }],
                    "isError": True
                }
        
        # Copy file
        @self.server.tool("copy-file", CopyFileInput)
        async def copy_file(input_data):
            try:
                # First make a copy of the file
                request_body = {}
                if input_data.new_name:
                    request_body['name'] = input_data.new_name
                
                copy_response = drive_service.files().copy(
                    fileId=input_data.file_id,
                    body=request_body,
                    fields='id, name, parents'
                ).execute()
                
                new_file_id = copy_response.get('id')
                
                # If a destination folder was specified and it's different from current parent folder
                if input_data.destination_folder_id:
                    # Get the current parents
                    file = drive_service.files().get(
                        fileId=new_file_id,
                        fields='parents'
                    ).execute()
                    
                    # Move the file to the new folder
                    current_parents = ",".join(file.get('parents', []))
                    drive_service.files().update(
                        fileId=new_file_id,
                        removeParents=current_parents,
                        addParents=input_data.destination_folder_id,
                        fields='id, name, parents, webViewLink'
                    ).execute()
                
                # Get the final file with link
                final_file = drive_service.files().get(
                    fileId=new_file_id,
                    fields='id, name, webViewLink'
                ).execute()
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"File copied successfully!\nName: {final_file.get('name')}\nFile ID: {final_file.get('id')}\nLink: {final_file.get('webViewLink')}"
                    }]
                }
            except Exception as e:
                logger.error(f"Error copying file: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error copying file: {e}"
                    }],
                    "isError": True
                }
        
        # Download file (base64)
        @self.server.tool("download-file-base64", DownloadFileBase64Input)
        async def download_file_base64(input_data):
            try:
                # Get file metadata
                file_metadata = drive_service.files().get(
                    fileId=input_data.file_id,
                    fields='name,mimeType'
                ).execute()
                
                # Get file content
                request = drive_service.files().get_media(fileId=input_data.file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                
                # Get the file content and convert to base64
                file_content = fh.getvalue()
                base64_content = base64.b64encode(file_content).decode('utf-8')
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"File downloaded successfully!\nName: {file_metadata.get('name')}\nMIME Type: {file_metadata.get('mimeType')}\nSize: {len(file_content)} bytes\nBase64 Content: {base64_content[:100]}..."
                    }],
                    # Return the full data through the custom field
                    "fileData": {
                        "name": file_metadata.get('name'),
                        "mimeType": file_metadata.get('mimeType'),
                        "base64Content": base64_content,
                        "size": len(file_content)
                    }
                }
            except Exception as e:
                logger.error(f"Error downloading file: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error downloading file: {e}"
                    }],
                    "isError": True
                }
        
        # Share drive item
        @self.server.tool("share-drive-item", ShareDriveItemInput)
        async def share_drive_item(input_data):
            try:
                # Get the name of the file/folder to include in the response
                file_metadata = drive_service.files().get(
                    fileId=input_data.file_id,
                    fields='name,mimeType'
                ).execute()
                
                # Create the permission
                user_permission = {
                    'type': 'user',
                    'role': input_data.role,
                    'emailAddress': input_data.email_address
                }
                
                response = drive_service.permissions().create(
                    fileId=input_data.file_id,
                    body=user_permission,
                    sendNotificationEmail=input_data.send_notification_email,
                    emailMessage=input_data.message,
                    fields='id,type,role,emailAddress'
                ).execute()
                
                # Get the item type (file or folder)
                item_type = "Folder" if file_metadata.get('mimeType') == 'application/vnd.google-apps.folder' else "File"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"{item_type} \"{file_metadata.get('name')}\" successfully shared with {input_data.email_address} as {input_data.role}.\nPermission ID: {response.get('id')}"
                    }]
                }
            except Exception as e:
                logger.error(f"Error sharing file: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error sharing file: {e}"
                    }],
                    "isError": True
                }
        
        # List permissions
        @self.server.tool("list-permissions", ListPermissionsInput)
        async def list_permissions(input_data):
            try:
                # Get the name of the file/folder to include in the response
                file_metadata = drive_service.files().get(
                    fileId=input_data.file_id,
                    fields='name,mimeType'
                ).execute()
                
                # List all permissions
                response = drive_service.permissions().list(
                    fileId=input_data.file_id,
                    fields='permissions(id,type,role,emailAddress,displayName,domain)'
                ).execute()
                
                permissions = response.get('permissions', [])
                item_type = "Folder" if file_metadata.get('mimeType') == 'application/vnd.google-apps.folder' else "File"
                
                content = f"Permissions for {item_type} \"{file_metadata.get('name')}\" ({input_data.file_id}):\n\n"
                
                if not permissions:
                    content += "No permissions found (other than owner)."
                else:
                    for permission in permissions:
                        content += f"ID: {permission.get('id')}\n"
                        content += f"Type: {permission.get('type')}\n"
                        content += f"Role: {permission.get('role')}\n"
                        
                        if permission.get('emailAddress'):
                            content += f"Email: {permission.get('emailAddress')}\n"
                        
                        if permission.get('displayName'):
                            content += f"Name: {permission.get('displayName')}\n"
                        
                        if permission.get('domain'):
                            content += f"Domain: {permission.get('domain')}\n"
                        
                        content += "\n"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": content
                    }]
                }
            except Exception as e:
                logger.error(f"Error listing permissions: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error listing permissions: {e}"
                    }],
                    "isError": True
                }
        
        # Create document
        @self.server.tool("create-doc", CreateDocInput)
        async def create_doc(input_data):
            try:
                # Create a new document
                doc = docs_service.documents().create(
                    body={
                        'title': input_data.title
                    }
                ).execute()
                
                document_id = doc.get('documentId')
                
                # If content was provided, add it to the document
                if input_data.content:
                    docs_service.documents().batchUpdate(
                        documentId=document_id,
                        body={
                            'requests': [
                                {
                                    'insertText': {
                                        'location': {
                                            'index': 1
                                        },
                                        'text': input_data.content
                                    }
                                }
                            ]
                        }
                    ).execute()
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Document created successfully!\nTitle: {input_data.title}\nDocument ID: {document_id}\nYou can now reference this document using: googledocs://{document_id}"
                    }]
                }
            except Exception as e:
                logger.error(f"Error creating document: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error creating document: {e}"
                    }],
                    "isError": True
                }
        
        # Update document
        @self.server.tool("update-doc", UpdateDocInput)
        async def update_doc(input_data):
            try:
                # Ensure doc_id is a string and not None
                if not input_data.doc_id:
                    raise ValueError("Document ID is required")
                
                if input_data.replace_all:
                    # First, get the document to find its length
                    doc = docs_service.documents().get(
                        documentId=input_data.doc_id
                    ).execute()
                    
                    # Calculate the document length
                    document_length = 1  # Start at 1 (the first character position)
                    if doc.get('body') and doc.get('body').get('content'):
                        for element in doc['body']['content']:
                            if 'paragraph' in element:
                                for paragraph_element in element['paragraph']['elements']:
                                    if 'textRun' in paragraph_element and 'content' in paragraph_element['textRun']:
                                        document_length += len(paragraph_element['textRun']['content'])
                    
                    # Delete all content and then insert new content
                    docs_service.documents().batchUpdate(
                        documentId=input_data.doc_id,
                        body={
                            'requests': [
                                {
                                    'deleteContentRange': {
                                        'range': {
                                            'startIndex': 1,
                                            'endIndex': document_length
                                        }
                                    }
                                },
                                {
                                    'insertText': {
                                        'location': {
                                            'index': 1
                                        },
                                        'text': input_data.content
                                    }
                                }
                            ]
                        }
                    ).execute()
                else:
                    # Append content to the end of the document
                    doc = docs_service.documents().get(
                        documentId=input_data.doc_id
                    ).execute()
                    
                    # Calculate the document length to append at the end
                    document_length = 1  # Start at 1 (the first character position)
                    if doc.get('body') and doc.get('body').get('content'):
                        for element in doc['body']['content']:
                            if 'paragraph' in element:
                                for paragraph_element in element['paragraph']['elements']:
                                    if 'textRun' in paragraph_element and 'content' in paragraph_element['textRun']:
                                        document_length += len(paragraph_element['textRun']['content'])
                    
                    # Append content at the end
                    docs_service.documents().batchUpdate(
                        documentId=input_data.doc_id,
                        body={
                            'requests': [
                                {
                                    'insertText': {
                                        'location': {
                                            'index': document_length
                                        },
                                        'text': input_data.content
                                    }
                                }
                            ]
                        }
                    ).execute()
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Document updated successfully!\nDocument ID: {input_data.doc_id}"
                    }]
                }
            except Exception as e:
                logger.error(f"Error updating document: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error updating document: {e}"
                    }],
                    "isError": True
                }
        
        # Search documents
        @self.server.tool("search-docs", SearchDocsInput)
        async def search_docs(input_data):
            try:
                response = drive_service.files().list(
                    q=f"mimeType='application/vnd.google-apps.document' and fullText contains '{input_data.query}'",
                    fields="files(id, name, createdTime, modifiedTime)",
                    pageSize=10
                ).execute()
                
                files = response.get('files', [])
                content = f"Search results for \"{input_data.query}\":\n\n"
                
                if not files:
                    content += "No documents found matching your query."
                else:
                    for file in files:
                        content += f"Title: {file.get('name')}\n"
                        content += f"ID: {file.get('id')}\n"
                        content += f"Created: {file.get('createdTime')}\n"
                        content += f"Last Modified: {file.get('modifiedTime')}\n\n"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": content
                    }]
                }
            except Exception as e:
                logger.error(f"Error searching documents: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error searching documents: {e}"
                    }],
                    "isError": True
                }
        
        # Delete document
        @self.server.tool("delete-doc", DeleteDocInput)
        async def delete_doc(input_data):
            try:
                # Get the document title first for confirmation
                doc = docs_service.documents().get(
                    documentId=input_data.doc_id
                ).execute()
                title = doc.get('title')
                
                # Delete the document
                drive_service.files().delete(
                    fileId=input_data.doc_id
                ).execute()
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Document \"{title}\" (ID: {input_data.doc_id}) has been successfully deleted."
                    }]
                }
            except Exception as e:
                logger.error(f"Error deleting document {input_data.doc_id}: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error deleting document: {e}"
                    }],
                    "isError": True
                }
        
        # Export document
        @self.server.tool("export-doc", ExportDocInput)
        async def export_doc(input_data):
            try:
                # Get the document metadata
                doc_metadata = drive_service.files().get(
                    fileId=input_data.doc_id,
                    fields='name,mimeType'
                ).execute()
                
                # Check if it's a Google Doc
                if doc_metadata.get('mimeType') != 'application/vnd.google-apps.document':
                    raise ValueError('The provided ID is not a Google Doc')
                
                # Map format to mimeType
                mime_type_map = {
                    'pdf': 'application/pdf',
                    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'txt': 'text/plain',
                    'html': 'text/html',
                    'odt': 'application/vnd.oasis.opendocument.text',
                    'rtf': 'application/rtf',
                    'epub': 'application/epub+zip'
                }
                
                # Export the file
                response = drive_service.files().export_media(
                    fileId=input_data.doc_id,
                    mimeType=mime_type_map[input_data.format]
                ).execute()
                
                # Create base64 of the content
                base64_content = base64.b64encode(response).decode('utf-8')
                
                # Generate export filename
                original_name = doc_metadata.get('name') or 'document'
                export_name = f"{original_name}.{input_data.format}"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Google Doc successfully exported to {input_data.format.upper()} format.\nOriginal document: {original_name}\nExported as: {export_name}\nSize: {len(response)} bytes"
                    }],
                    "exportData": {
                        "name": export_name,
                        "mimeType": mime_type_map[input_data.format],
                        "base64Content": base64_content
                    }
                }
            except Exception as e:
                logger.error(f"Error exporting document: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error exporting document: {e}"
                    }],
                    "isError": True
                }
        
        # Batch upload
        @self.server.tool("upload-batch", UploadBatchInput)
        async def upload_batch(input_data):
            try:
                results = []
                errors = []
                
                # Process each file
                for file in input_data.files:
                    try:
                        # Create a temporary file path
                        temp_path = get_temp_file('batch-upload-')
                        
                        # Decode and write content to temp file
                        file_content = base64.b64decode(file.base64_content)
                        with open(temp_path, 'wb') as f:
                            f.write(file_content)
                        
                        # Setup file metadata
                        file_metadata = {
                            'name': file.name
                        }
                        
                        if input_data.folder_id:
                            file_metadata['parents'] = [input_data.folder_id]
                        
                        # Upload the file
                        media = MediaFileUpload(
                            temp_path,
                            mimetype=file.mime_type,
                            resumable=True
                        )
                        
                        response = drive_service.files().create(
                            body=file_metadata,
                            media_body=media,
                            fields='id,name,webViewLink'
                        ).execute()
                        
                        # Clean up
                        os.unlink(temp_path)
                        
                        # Save the result
                        results.append({
                            'name': file.name,
                            'id': response.get('id'),
                            'link': response.get('webViewLink')
                        })
                    except Exception as err:
                        errors.append({
                            'name': file.name,
                            'error': str(err)
                        })
                
                # Build response content
                content = "Batch upload results:\n\n"
                content += f"Successfully uploaded {len(results)} of {len(input_data.files)} files.\n\n"
                
                if results:
                    content += "Successful uploads:\n"
                    for result in results:
                        content += f"- {result['name']}: {result['id']} ({result['link']})\n"
                    content += "\n"
                
                if errors:
                    content += "Failed uploads:\n"
                    for error in errors:
                        content += f"- {error['name']}: {error['error']}\n"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": content
                    }],
                    "uploadResults": {
                        "successful": results,
                        "failed": errors
                    }
                }
            except Exception as e:
                logger.error(f"Error in batch upload: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error in batch upload: {e}"
                    }],
                    "isError": True
                }
        
        # Send file content email
        @self.server.tool("send-file-email", SendFileContentEmailInput)
        async def send_file_email(input_data):
            try:
                # Create email configuration from input, config file, or environment variables
                if any([input_data.smtp_server, input_data.smtp_port, input_data.smtp_user, input_data.smtp_password, input_data.sender_email]):
                    # Use input parameters if provided
                    email_config = EmailConfig(
                        smtp_server=input_data.smtp_server,
                        smtp_port=input_data.smtp_port,
                        smtp_user=input_data.smtp_user,
                        smtp_password=input_data.smtp_password,
                        sender_email=input_data.sender_email
                    )
                else:
                    # Use global config loaded from config file
                    email_config = EMAIL_CONFIG
                
                # Check for required file
                if not os.path.exists(input_data.file_path):
                    raise FileNotFoundError(f"File not found: {input_data.file_path}")
                
                # Send the email
                success = send_file_content_email(
                    email_config,
                    input_data.to_email,
                    input_data.subject,
                    input_data.file_path,
                    input_data.cc_emails,
                    input_data.include_dummy_stl
                )
                
                if success:
                    return {
                        "content": [{
                            "type": "text",
                            "text": f"Email sent successfully!\n\nTo: {input_data.to_email}\nSubject: {input_data.subject}\nFile: {os.path.basename(input_data.file_path)}\nIncluded dummy STL: {'Yes' if input_data.include_dummy_stl else 'No'}"
                        }]
                    }
                else:
                    return {
                        "content": [{
                            "type": "text",
                            "text": "Failed to send email. Check SMTP settings and ensure they are correctly configured in config.json, environment variables, or provided in the request."
                        }],
                        "isError": True
                    }
            except Exception as e:
                logger.error(f"Error sending email: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error sending email: {e}"
                    }],
                    "isError": True
                }
        
        # Upload file from URL
        @self.server.tool("upload-file-from-url", UploadFileFromUrlInput)
        async def upload_file_from_url(input_data):
            try:
                import urllib.request
                
                # Create a temporary file path
                temp_path = get_temp_file('upload-url-')
                
                # Fetch the file content from URL
                try:
                    urllib.request.urlretrieve(input_data.url, temp_path)
                except Exception as url_error:
                    raise ValueError(f"Failed to fetch file from URL: {str(url_error)}")
                
                # Set up file metadata
                file_metadata = {
                    'name': input_data.name
                }
                
                if input_data.description:
                    file_metadata['description'] = input_data.description
                
                if input_data.folder_id:
                    file_metadata['parents'] = [input_data.folder_id]
                
                # Upload the file
                media = MediaFileUpload(
                    temp_path,
                    mimetype=input_data.mime_type,
                    resumable=True
                )
                
                response = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, name, webViewLink, mimeType, size'
                ).execute()
                
                # Clean up the temporary file
                os.unlink(temp_path)
                
                # Format size information
                size_str = f"{response.get('size', 'unknown')} bytes"
                if response.get('size'):
                    size_bytes = int(response.get('size'))
                    if size_bytes > 1024 * 1024:
                        size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
                    elif size_bytes > 1024:
                        size_str = f"{size_bytes / 1024:.2f} KB"
                
                return {
                    "content": [{
                        "type": "text",
                        "text": f"File uploaded successfully from URL!\nName: {response.get('name')}\nFile ID: {response.get('id')}\nType: {response.get('mimeType')}\nSize: {size_str}\nLink: {response.get('webViewLink')}"
                    }]
                }
            except Exception as e:
                logger.error(f"Error uploading file from URL: {e}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error uploading file from URL: {e}"
                    }],
                    "isError": True
                }
    
    def register_prompts(self):
        """Register MCP prompts."""
        # Document creation prompt
        @self.server.prompt("create-doc-template", CreateDocTemplateInput)
        async def create_doc_template(input_data):
            return {
                "messages": [{
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"Please create a Google Doc with the title \"{input_data.title}\" about {input_data.subject} in a {input_data.style} writing style. Make sure it's well-structured with an introduction, main sections, and a conclusion."
                    }
                }]
            }
        
        # Document analysis prompt
        @self.server.prompt("analyze-doc", AnalyzeDocInput)
        async def analyze_doc(input_data):
            return {
                "messages": [{
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"Please analyze the content of the document with ID {input_data.doc_id}. Provide a summary of its content, structure, key points, and any suggestions for improvement."
                    }
                }]
            }
        
        # Folder structure prompt
        @self.server.prompt("create-folder-structure", CreateFolderStructureInput)
        async def create_folder_structure(input_data):
            return {
                "messages": [{
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"I need to create a well-organized folder structure in Google Drive for a {input_data.project_type} project called \"{input_data.project_name}\". Please suggest an appropriate folder hierarchy with subfolders that would help keep files organized. Include folder names and a brief description of what should go in each folder."
                    }
                }]
            }
    
    async def start(self):
        """Start the MCP server."""
        # Initialize Google API services
        success = init_services()
        if not success:
            logger.error("Failed to initialize Google API services. Server will not work correctly.")
        else:
            logger.info("Google API services initialized successfully.")
        
        # Create a transport for communicating over stdin/stdout
        transport = McpStdio()
        
        # Connect the server to the transport
        await self.server.connect(transport)
        
        logger.info("Google Drive & Docs MCP Server running on stdio")


if __name__ == "__main__":
    import asyncio
    
    # Create and start the server
    server = GoogleDriveMcpServer()
    
    # Run the server
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")