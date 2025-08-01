#!/bin/bash

echo "🎬 Starting YouTube Downloader..."
echo "📱 Access the website at: http://localhost:8080"
echo "🌐 Or from other devices on your network at: http://$(ipconfig getifaddr en0):8080"
echo "⏹️  Press Ctrl+C to stop the server"
echo ""

# Activate virtual environment and start the Flask app
source venv/bin/activate
python app.py
