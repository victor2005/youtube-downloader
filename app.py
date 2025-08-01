from flask import Flask, render_template, request, jsonify, send_file, session
from flask_compress import Compress
import yt_dlp
import os
import tempfile
import threading
import time
from pathlib import Path
import logging
import uuid
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logging.warning("pydub not available - audio conversion will be limited")

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# Enable compression
Compress(app)

# Add cache headers for static content
@app.after_request
def after_request(response):
    # Add cache headers for static files
    if request.endpoint == 'static':
        response.cache_control.max_age = 31536000  # 1 year
    else:
        response.cache_control.max_age = 300  # 5 minutes for dynamic content
    
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    return response

# Store download progress and user files
download_progress = {}
user_downloads = {}  # session_id -> list of files

def convert_to_mp3(input_file, output_file):
    """Convert audio file to MP3 using pydub"""
    try:
        if not PYDUB_AVAILABLE:
            return False
        
        # Load the audio file
        if input_file.suffix.lower() == '.webm':
            audio = AudioSegment.from_file(str(input_file), format="webm")
        elif input_file.suffix.lower() == '.m4a':
            audio = AudioSegment.from_file(str(input_file), format="m4a")
        else:
            audio = AudioSegment.from_file(str(input_file))
        
        # Export as MP3
        audio.export(str(output_file), format="mp3", bitrate="192k")
        return True
    except Exception as e:
        logging.error(f"Audio conversion failed: {e}")
        return False

class ProgressHook:
    def __init__(self, download_id):
        self.download_id = download_id
    
    def __call__(self, d):
        try:
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', 'N/A')
                speed = d.get('_speed_str', 'N/A')
                download_progress[self.download_id] = {
                    'status': 'downloading',
                    'percent': percent,
                    'speed': speed
                }
                logging.info(f"Progress {self.download_id}: {percent} at {speed}")
            elif d['status'] == 'finished':
                download_progress[self.download_id] = {
                    'status': 'finished',
                    'filename': d.get('filename', 'unknown')
                }
                logging.info(f"Download {self.download_id} finished: {d.get('filename', 'unknown')}")
        except Exception as e:
            logging.error(f"Progress hook error for {self.download_id}: {e}")

@app.route('/')
def index():
    # Initialize session if not exists
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        user_downloads[session['user_id']] = []
    
    return render_template('index.html')

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'youtube-downloader'})

@app.route('/ping')
def ping():
    """Simple ping endpoint for uptime monitoring"""
    return 'pong', 200

@app.route('/download', methods=['POST'])
def download():
    try:
        data = request.json
        url = data.get('url')
        format_type = data.get('format', 'video')  # 'video' or 'mp3'
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Generate unique download ID
        download_id = str(int(time.time() * 1000))
        
        logging.info(f"Starting download for URL: {url}, format: {format_type}")
        
        # Ensure user has session
        if 'user_id' not in session:
            session['user_id'] = str(uuid.uuid4())
            user_downloads[session['user_id']] = []
        
        user_id = session['user_id']
        
        # Start download in background thread
        thread = threading.Thread(target=download_video, args=(url, format_type, download_id, user_id))
        thread.daemon = True  # Make thread daemon so it doesn't block shutdown
        thread.start()
        
        return jsonify({'download_id': download_id})
    except Exception as e:
        logging.error(f"Error in download endpoint: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def download_video(url, format_type, download_id, user_id):
    try:
        logging.info(f"Processing download {download_id}: {url} for user {user_id}")
        
        # Update progress to show we're starting
        download_progress[download_id] = {
            'status': 'initializing',
            'message': 'Initializing download...'
        }
        
        # Create user-specific downloads directory
        downloads_dir = Path('downloads') / user_id
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # Find and validate FFmpeg
        ffmpeg_location = None
        ffmpeg_working = False
        
        # Try to find ffmpeg in PATH first
        import shutil
        import subprocess
        
        ffmpeg_location = shutil.which('ffmpeg')
        
        if not ffmpeg_location:
            # Fallback to common paths
            possible_paths = [
                '/usr/bin/ffmpeg', 
                '/usr/local/bin/ffmpeg', 
                '/opt/homebrew/bin/ffmpeg',
                '/nix/store/*/bin/ffmpeg'  # Nix store path pattern
            ]
            for path in possible_paths:
                if '*' in path:
                    # Handle Nix store pattern
                    import glob
                    matches = glob.glob(path)
                    if matches:
                        ffmpeg_location = matches[0]
                        break
                elif os.path.exists(path):
                    ffmpeg_location = path
                    break
        
        # Test if FFmpeg actually works
        if ffmpeg_location:
            try:
                result = subprocess.run([ffmpeg_location, '-version'], 
                                      capture_output=True, timeout=5)
                ffmpeg_working = result.returncode == 0
                logging.info(f"FFmpeg at {ffmpeg_location} - Working: {ffmpeg_working}")
            except Exception as e:
                logging.warning(f"FFmpeg test failed: {e}")
                ffmpeg_working = False
        else:
            logging.warning("FFmpeg not found in any location")
        logging.info(f"Download format requested: {format_type}")
        
        # Update progress to show we're preparing
        download_progress[download_id] = {
            'status': 'preparing',
            'message': 'Preparing download...'
        }
        
        # Configure yt-dlp options with better error handling
        base_opts = {
            'outtmpl': str(downloads_dir / '%(title)s.%(ext)s'),
            'progress_hooks': [ProgressHook(download_id)],
            'no_warnings': False,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 3,
        }
        
        if ffmpeg_working:
            base_opts['ffmpeg_location'] = ffmpeg_location
        
        if format_type == 'mp3':
            if ffmpeg_working:
                # FFmpeg available and working - convert to MP3
                logging.info(f"Converting to MP3 using FFmpeg at {ffmpeg_location}")
                ydl_opts = {
                    **base_opts,
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                }
            else:
                # FFmpeg not working - download audio for custom conversion
                logging.info("FFmpeg not available - will use custom conversion to MP3")
                ydl_opts = {
                    **base_opts,
                    'format': 'bestaudio/best',
                }
        else:
            ydl_opts = {
                **base_opts,
                'format': 'best[height<=720]/best[height<=480]/best',
            }
        
        logging.info(f"Starting yt-dlp download with options: {ydl_opts}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        logging.info(f"Download completed, checking files in {downloads_dir}")
        
        # Initialize user downloads if needed
        if user_id not in user_downloads:
            user_downloads[user_id] = []
        
        try:
            # Post-process for MP3 conversion if needed
            if format_type == 'mp3' and not ffmpeg_working and PYDUB_AVAILABLE:
                logging.info("Starting custom MP3 conversion...")
                # Update progress to show conversion
                download_progress[download_id] = {
                    'status': 'converting',
                    'message': 'Converting to MP3...'
                }
                converted_files = []
            
            for file_path in downloads_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in ['.webm', '.m4a', '.ogg']:
                    mp3_path = file_path.with_suffix('.mp3')
                    logging.info(f"Converting {file_path.name} to {mp3_path.name}")
                    
                    if convert_to_mp3(file_path, mp3_path):
                        # Conversion successful - remove original and track MP3
                        file_path.unlink()
                        logging.info(f"Successfully converted to MP3: {mp3_path.name}")
                        converted_files.append(mp3_path)
                    else:
                        logging.warning(f"Conversion failed, keeping original: {file_path.name}")
                        converted_files.append(file_path)
            
            # Add only the final converted files to user's list
            for file_path in converted_files:
                if file_path.exists():
                    file_info = {
                        'name': file_path.name,
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime,
                        'user_id': user_id
                    }
                    # Avoid duplicates
                    if not any(f['name'] == file_info['name'] for f in user_downloads[user_id]):
                        user_downloads[user_id].append(file_info)
            
            # Update progress to show completion
            download_progress[download_id] = {
                'status': 'finished',
                'message': 'MP3 conversion completed!'
            }
        else:
            # For non-MP3 downloads or when FFmpeg is working, add all files normally
            for file_path in downloads_dir.iterdir():
                if file_path.is_file():
                    file_info = {
                        'name': file_path.name,
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime,
                        'user_id': user_id
                    }
                    # Avoid duplicates
                    if not any(f['name'] == file_info['name'] for f in user_downloads[user_id]):
                        user_downloads[user_id].append(file_info)
            
        logging.info(f"Download {download_id} completed successfully")
            
    except Exception as e:
        logging.error(f"Download {download_id} failed: {str(e)}")
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
    # Ensure user has session
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        user_downloads[session['user_id']] = []
    
    user_id = session['user_id']
    
    # Get user's downloads from memory first
    if user_id in user_downloads:
        files = user_downloads[user_id].copy()
    else:
        files = []
        user_downloads[user_id] = []
    
    # Also check user's directory for any files
    user_downloads_dir = Path('downloads') / user_id
    if user_downloads_dir.exists():
        for file_path in user_downloads_dir.iterdir():
            if file_path.is_file():
                file_info = {
                    'name': file_path.name,
                    'size': file_path.stat().st_size,
                    'modified': file_path.stat().st_mtime
                }
                # Avoid duplicates
                if not any(f['name'] == file_info['name'] for f in files):
                    files.append(file_info)
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify(files)

@app.route('/download-file/<filename>')
def download_file(filename):
    # Ensure user has session
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    user_downloads_dir = Path('downloads') / user_id
    file_path = user_downloads_dir / filename
    
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(str(file_path), as_attachment=True)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
