# Python Google Drive MCP Server

This is a Python implementation of the Model Context Protocol (MCP) server for Google Drive and Google Docs integration.

## Features

- **Google Drive Features:**
  - List files and folders in your Drive
  - Create new folders with custom names and hierarchies
  - Upload files (from base64, from URLs, or batch uploads)
  - Download files as base64
  - Copy files within your Drive
  - Share files and folders with specific users
  - List permissions on files and folders
  - Export Google Docs to different formats (PDF, DOCX, etc.)

- **Google Docs Features:**
  - List all Google Docs in your Drive
  - Read the content of specific documents
  - Create new documents
  - Update existing documents
  - Search for documents
  - Delete documents
  
- **Email Features:**
  - Send emails with file contents
  - Automatically attach files to emails
  - Include dummy STL attachments
  - Support for CC recipients

## Installation

1. Set up a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Ensure you have valid Google OAuth 2.0 credentials:
   - The application expects `credentials.json` in the parent directory
   - On first run, it will create a `token.json` file after authentication

## Usage

### Starting the Server

```bash
python server.py
```

The server runs on stdin/stdout, which is the format expected by the MCP protocol. It authenticates with Google on first run.

### Email Configuration

There are three ways to configure email settings:

1. Using a config file (recommended):

Edit the `config.json` file in the python_mcp_gdrive directory:

```json
{
    "email": {
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "your-email@example.com",
        "smtp_password": "your-app-password",
        "sender_email": "your-name@example.com",
        "use_tls": true
    }
}
```

2. Using environment variables:

```bash
export SMTP_SERVER=smtp.example.com
export SMTP_PORT=587
export SMTP_USER=your-email@example.com
export SMTP_PASSWORD=your-password
export SENDER_EMAIL=your-name@example.com
```

3. Providing settings directly when using the `send-file-email` tool.

The system will first check for settings in the tool parameters, then in the config file, and finally in environment variables.

### Testing File Upload

To test uploading a file to Google Drive:

```bash
python upload_test.py <path_to_file> [folder_id]
```

For example:

```bash
python upload_test.py ../mcp_test/test3/test3.txt
```

### Testing Email Sending

There are multiple ways to test the email functionality:

1. Using the simplified test script (uses config.json):

```bash
python send_test_email.py
```

2. Using the config-based test script:

```bash
python email_test_config.py --file <path_to_file> --to recipient@example.com [options]
```

For example:

```bash
python email_test_config.py --file ../mcp_test/test4/test4.txt --to recipient@example.com --subject "Test Email"
```

3. Using the original test script with command-line options:

```bash
python email_test.py --file <path_to_file> --to recipient@example.com --server smtp.example.com --port 587 --user your-email@example.com --password "your-password" [other options]
```

## Connecting to Claude

To use this server with Claude:

1. Configure the MCP server in your Claude configuration
2. Point Claude to the server.py script
3. Use the provided prompts and tools to interact with Google Drive and Docs

## Available Resources and Tools

The server implements the same resources, tools, and prompts as the JavaScript version, including:

- Resource for listing documents: `googledocs://list`
- Resource for getting document content: `googledocs://{docId}`
- Resource for listing Drive files: `googledrive://files{/folderId}{?query,mimetype}`
- Resource for getting file details: `googledrive://file/{fileId}`

And tools like:
- `create-folder`
- `list-folders`
- `upload-file-base64`
- `download-file-base64`
- And many more!

## License

MIT