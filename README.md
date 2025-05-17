# Google Drive and Docs MCP Server

This repository contains a Python implementation of a Model Context Protocol (MCP) server that allows you to connect to Google Drive and Google Docs through Claude.

With this server, you can:

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

## Prerequisites

- Python 3.7 or later
- Google Cloud project with the Google Docs API and Google Drive API enabled
- OAuth 2.0 credentials for your Google Cloud project

## Setup

1. Clone this repository and navigate to the project directory:

```bash
git clone https://github.com/yourusername/MCP-Google-Doc.git
cd MCP-Google-Doc
```

2. Navigate to the Python implementation directory:

```bash
cd python_mcp_gdrive
```

3. Set up a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

Alternatively, you can run the setup script:

```bash
./setup.sh
```

3. Create an OAuth 2.0 client ID in the Google Cloud Console:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Docs API and Google Drive API
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop app" for the application type
   - Download the JSON file and save it as `credentials.json` in your project directory

   > **Important**: The `credentials.json` and `token.json` files contain sensitive information and are excluded from version control via `.gitignore`. Never commit these files to your repository.

4. Build the project:

```bash
npm run build
```

5. Run the server:

```bash
npm start
```

The first time you run the server, it will prompt you to authenticate with Google. Follow the on-screen instructions to authorize the application. This will generate a `token.json` file that stores your access tokens.

## Security Considerations

- **Credential Security**: Both `credentials.json` and `token.json` contain sensitive information and should never be shared or committed to version control. They are already added to the `.gitignore` file.
- **Token Refresh**: The application automatically refreshes the access token when it expires.
- **Revoking Access**: If you need to revoke access, delete the `token.json` file and go to your [Google Account Security settings](https://myaccount.google.com/security) to remove the app from your authorized applications.

## Connecting to Claude for Desktop

To use this server with Claude for Desktop:

1. Edit your Claude Desktop configuration file:
   - On macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - On Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the following configuration:

```json
{
  "mcpServers": {
    "google-drive": {
      "command": "python",
      "args": ["/absolute/path/to/python_mcp_gdrive/server.py"]
    }
  }
}
```

Replace `/absolute/path/to/python_mcp_gdrive/server.py` with the actual path to your Python server.py file.

3. Restart Claude for Desktop.

## Development

### Project Structure

```
google-drive-mcp/
├── python_mcp_gdrive/    # Python implementation
│   ├── server.py         # Python MCP server implementation
│   ├── gdrive_test.py    # Google Drive test script
│   ├── requirements.txt  # Python dependencies
│   ├── setup.sh          # Python setup script
│   └── README.md         # Python implementation documentation
├── mcp_test/             # Test files
│   ├── test3/            # Test directory with sample file
│   └── test4/            # Test directory with sample file
├── credentials.json      # OAuth 2.0 credentials (not in version control)
├── README.md             # Project documentation
└── token.json            # OAuth tokens (not in version control)
```

### Adding New Features

To add new features to the Python MCP server:

1. Modify the `python_mcp_gdrive/server.py` file to implement new functionality
2. Test your changes by running `python python_mcp_gdrive/server.py`
3. For testing Google Drive operations, you can use `python python_mcp_gdrive/gdrive_test.py`

## Available Resources

### Google Docs Resources
- `googledocs://list` - Lists all Google Docs in your Drive
- `googledocs://{docId}` - Gets the content of a specific document by ID

### Google Drive Resources
- `googledrive://files{/folderId}{?query,mimetype}` - Lists files in Google Drive, optionally filtered by folder, search query, or file type
- `googledrive://file/{fileId}` - Gets detailed information about a specific file or folder

## Available Tools

### Google Docs Tools
- `create-doc` - Creates a new Google Doc with the specified title and optional content
- `update-doc` - Updates an existing Google Doc with new content (append or replace)
- `search-docs` - Searches for Google Docs containing specific text
- `delete-doc` - Deletes a Google Doc by ID
- `export-doc` - Exports a Google Doc to a different format (PDF, DOCX, TXT, HTML, etc.)

### Google Drive Tools
- `list-folders` - Lists folders in Google Drive, optionally within a specific parent folder
- `create-folder` - Creates a new folder in Google Drive with an optional parent folder
- `upload-file-base64` - Uploads a file to Google Drive from base64-encoded content
- `upload-file-from-url` - Uploads a file to Google Drive from a URL
- `upload-batch` - Uploads multiple files to Google Drive in a single operation
- `download-file-base64` - Downloads a file from Google Drive as base64-encoded content
- `copy-file` - Creates a copy of a file within Google Drive
- `share-drive-item` - Shares a file or folder with a specific user
- `list-permissions` - Lists all permissions on a file or folder

## Available Prompts

- `create-doc-template` - Helps create a new document based on a specified topic and writing style
- `analyze-doc` - Analyzes the content of a document and provides a summary
- `create-folder-structure` - Suggests a folder structure for a project based on its type

## Usage Examples

Here are some example prompts you can use with Claude once the server is connected:

### Google Docs Examples
- "Show me a list of all my Google Docs"
- "Create a new Google Doc titled 'Meeting Notes' with the content 'Topics to discuss: ...'"
- "Update my document with ID '1abc123def456' to add this section at the end: ..."
- "Search my Google Docs for any documents containing 'project proposal'"
- "Delete the Google Doc with ID '1abc123def456'"
- "Create a formal document about climate change"
- "Analyze the content of document with ID '1abc123def456'"
- "Export my Google Doc with ID '1abc123def456' to PDF format"

### Google Drive Examples
- "Show me all folders in my Google Drive"
- "Create a new folder called 'Project Assets' in my Google Drive"
- "Upload this image to my Google Drive" (with file data)
- "Upload a file from this URL to my Google Drive: https://example.com/file.pdf"
- "Download the file with ID '1abc123def456' from my Google Drive"
- "Make a copy of the file with ID '1abc123def456' in my 'Backups' folder"
- "Share my file with ID '1abc123def456' with user@example.com as an editor"
- "Who has access to my file with ID '1abc123def456'?"
- "Suggest a folder structure for my new marketing project called 'Q1 Campaign'"

## Troubleshooting

If you encounter authentication issues:
1. Delete the `token.json` file in your project directory
2. Run the server again to trigger a new authentication flow

If you're having trouble with the Google Docs API:
1. Make sure the API is enabled in your Google Cloud Console
2. Check that your OAuth credentials have the correct scopes

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Submit a pull request

## License

MIT