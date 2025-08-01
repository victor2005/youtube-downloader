# 🎬 YouTube Downloader

A simple web application that allows you to download YouTube videos or extract MP3 audio using yt-dlp.

## Features

- 🎥 Download YouTube videos in MP4 format
- 🎵 Extract audio as MP3 files
- 📊 Real-time download progress tracking
- 📁 File management with download history
- 🌐 Web-based interface accessible from any device on your network

## Setup

1. **Clone or create the project directory** (already done)

2. **Install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   ./start.sh
   ```
   
   Or manually:
   ```bash
   source venv/bin/activate
   python app.py
   ```

## Usage

1. Open your web browser and go to `http://localhost:8080`
2. Paste a YouTube URL in the input field
3. Choose your preferred format:
   - **Video (MP4)**: Downloads the full video
   - **Audio (MP3)**: Extracts only the audio
4. Click "Start Download"
5. Monitor the progress and download completed files

## Access from Other Devices

The server runs on all network interfaces, so you can access it from other devices on your network:
- Find your local IP address with: `ipconfig getifaddr en0`
- Access from other devices at: `http://YOUR_IP:8080`

## File Storage

Downloaded files are stored in the `downloads/` directory within the project folder.

## Dependencies

- **Flask**: Web framework
- **yt-dlp**: YouTube video/audio downloader
- **FFmpeg**: Required for MP3 extraction (should be installed on macOS)

## Notes

- The application uses port 8080 to avoid conflicts with macOS AirPlay (which uses port 5000)
- Downloads are processed in the background with real-time progress updates
- The interface is responsive and works on both desktop and mobile devices

## Troubleshooting

- If you get permission errors, make sure the start script is executable: `chmod +x start.sh`
- If downloads fail, try updating yt-dlp: `pip install --upgrade yt-dlp`
- For MP3 extraction issues, ensure FFmpeg is installed: `brew install ffmpeg`
