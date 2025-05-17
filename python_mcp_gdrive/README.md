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

### Testing File Upload

To test uploading a file to Google Drive:

```bash
python upload_test.py <path_to_file> [folder_id]
```

For example:

```bash
python upload_test.py ../mcp_test/test3/test3.txt
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