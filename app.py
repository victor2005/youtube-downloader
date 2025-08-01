from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import tempfile
import threading
import time
from pathlib import Path

app = Flask(__name__)

# Store download progress
download_progress = {}

class ProgressHook:
    def __init__(self, download_id):
        self.download_id = download_id
    
    def __call__(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', 'N/A')
            speed = d.get('_speed_str', 'N/A')
            download_progress[self.download_id] = {
                'status': 'downloading',
                'percent': percent,
                'speed': speed
            }
        elif d['status'] == 'finished':
            download_progress[self.download_id] = {
                'status': 'finished',
                'filename': d['filename']
            }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    format_type = data.get('format', 'video')  # 'video' or 'mp3'
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Generate unique download ID
    download_id = str(int(time.time() * 1000))
    
    # Start download in background thread
    thread = threading.Thread(target=download_video, args=(url, format_type, download_id))
    thread.start()
    
    return jsonify({'download_id': download_id})

def download_video(url, format_type, download_id):
    try:
        # Create downloads directory
        downloads_dir = Path('downloads')
        downloads_dir.mkdir(exist_ok=True)
        
        # Configure yt-dlp options
        if format_type == 'mp3':
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': str(downloads_dir / '%(title)s.%(ext)s'),
                'progress_hooks': [ProgressHook(download_id)],
            }
        else:
            ydl_opts = {
                'format': 'best[height<=720]/best',
                'outtmpl': str(downloads_dir / '%(title)s.%(ext)s'),
                'progress_hooks': [ProgressHook(download_id)],
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
    except Exception as e:
        download_progress[download_id] = {
            'status': 'error',
            'error': str(e)
        }

@app.route('/progress/<download_id>')
def get_progress(download_id):
    progress = download_progress.get(download_id, {'status': 'not_found'})
    return jsonify(progress)

@app.route('/downloads')
def list_downloads():
    downloads_dir = Path('downloads')
    if not downloads_dir.exists():
        return jsonify([])
    
    files = []
    for file_path in downloads_dir.iterdir():
        if file_path.is_file():
            files.append({
                'name': file_path.name,
                'size': file_path.stat().st_size,
                'modified': file_path.stat().st_mtime
            })
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify(files)

@app.route('/download-file/<filename>')
def download_file(filename):
    downloads_dir = Path('downloads')
    file_path = downloads_dir / filename
    
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(str(file_path), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
