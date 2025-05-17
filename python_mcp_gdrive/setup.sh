#!/bin/bash

# Setup script for Python Google Drive MCP

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Make scripts executable
echo "Making scripts executable..."
chmod +x server.py upload_test.py

echo "Setup complete. You can now run the server with:"
echo "./server.py"
echo ""
echo "To test file upload, use:"
echo "./upload_test.py <file_path> [folder_id]"
echo ""
echo "For example:"
echo "./upload_test.py ../mcp_test/test3/test3.txt"