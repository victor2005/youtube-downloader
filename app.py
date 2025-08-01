from flask import Flask, render_template, request, jsonify, send_file, session
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
progress_timestamps = {}  # track when progress was last updated

def cleanup_old_progress():
    """Clean up progress data older than 10 minutes"""
    import time
    current_time = time.time()
    old_keys = []
    
    for download_id, timestamp in progress_timestamps.items():
        if current_time - timestamp > 600:  # 10 minutes
            old_keys.append(download_id)
    
    for key in old_keys:
        download_progress.pop(key, None)
        progress_timestamps.pop(key, None)
        logging.info(f"Cleaned up old progress data for download {key}")

def update_progress(download_id, status_dict):
    """Update progress with timestamp"""
    import time
    download_progress[download_id] = status_dict
    progress_timestamps[download_id] = time.time()

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
            logging.info(f"Progress hook called for {self.download_id} with status: {d.get('status', 'unknown')}")
            
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
            else:
                # Log other statuses for debugging
                logging.info(f"Progress {self.download_id}: status={d.get('status')}, data={d}")
        except Exception as e:
            logging.error(f"Progress hook error for {self.download_id}: {e}")

@app.route('/')
def index():
    # Initialize session if not exists
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        user_downloads[session['user_id']] = []
        logging.info(f"Index page: Created new session with user_id: {session['user_id']}")
    else:
        logging.info(f"Index page: Using existing session with user_id: {session['user_id']}")
    
    return render_template('index.html')

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'youtube-downloader'})

@app.route('/ping')
def ping():
    """Simple ping endpoint for uptime monitoring"""
    return 'pong', 200

@app.route('/sw.js')
def serve_sw():
    """Serve PropellerAds service worker file"""
    return send_file('sw.js', mimetype='application/javascript')

@app.route('/test-ytdlp')
def test_ytdlp():
    """Test endpoint to check if yt-dlp is working"""
    try:
        import yt_dlp
        # Test with a simple, known working URL
        test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # Short test video
        
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(test_url, download=False)
            title = info.get('title', 'Unknown')
            duration = info.get('duration', 'Unknown')
            
        return jsonify({
            'status': 'success',
            'yt_dlp_version': yt_dlp.version.__version__,
            'test_title': title,
            'test_duration': duration
        })
    except Exception as e:
        logging.error(f"yt-dlp test failed: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/debug-status')
def debug_status():
    """Debug endpoint to check current status"""
    current_user_id = session.get('user_id', 'no_session')
    user_downloads_dir = Path('downloads') / current_user_id if current_user_id != 'no_session' else None
    
    files_on_disk = []
    if user_downloads_dir and user_downloads_dir.exists():
        files_on_disk = [f.name for f in user_downloads_dir.iterdir() if f.is_file()]
    
    return jsonify({
        'active_downloads': len(download_progress),
        'download_progress': download_progress,
        'user_downloads_count': len(user_downloads),
        'current_user_id': current_user_id,
        'user_downloads_in_memory': user_downloads.get(current_user_id, []),
        'files_on_disk': files_on_disk,
        'all_user_downloads': user_downloads  # Show all user download data
    })

@app.route('/session-info')
def session_info():
    """Simple session info endpoint"""
    return jsonify({
        'session_id': session.get('user_id', 'no_session'),
        'session_keys': list(session.keys())
    })

@app.route('/test-downloads')
def test_downloads():
    """Test endpoint to debug downloads without cache"""
    user_id = session.get('user_id', 'no_session')
    user_downloads_dir = Path('downloads') / user_id if user_id != 'no_session' else None
    
    files_on_disk = []
    if user_downloads_dir and user_downloads_dir.exists():
        files_on_disk = [{
            'name': f.name,
            'size': f.stat().st_size,
            'path': str(f)
        } for f in user_downloads_dir.iterdir() if f.is_file()]
    
    return jsonify({
        'session_user_id': user_id,
        'files_in_memory': user_downloads.get(user_id, []),
        'files_on_disk': files_on_disk,
        'directory_path': str(user_downloads_dir) if user_downloads_dir else 'no_session'
    })

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
            logging.info(f"Download endpoint: Created new session with user_id: {session['user_id']}")
        
        user_id = session['user_id']
        logging.info(f"Download endpoint: Using user_id: {user_id}")
        
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
        logging.info(f"STEP 1: Processing download {download_id}: {url} for user {user_id}")
        
        # Update progress to show we're starting
        update_progress(download_id, {
            'status': 'initializing',
            'message': 'Initializing download...'
        })
        logging.info(f"STEP 2: Set initializing status for {download_id}")
        
        # Create user-specific downloads directory
        downloads_dir = Path('downloads') / user_id
        downloads_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"STEP 3: Created downloads directory for {download_id}")
        
        # Find and validate FFmpeg
        ffmpeg_location = None
        ffmpeg_working = False
        logging.info(f"STEP 4: Starting FFmpeg detection for {download_id}")
        
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
        logging.info(f"STEP 5: Download format requested: {format_type}")
        
        # Update progress to show we're preparing
        update_progress(download_id, {
            'status': 'preparing',
            'message': 'Preparing download...'
        })
        logging.info(f"STEP 6: Set preparing status for {download_id}")
        
        # Configure yt-dlp options with better error handling
        base_opts = {
            'outtmpl': str(downloads_dir / '%(title)s.%(ext)s'),
            'progress_hooks': [ProgressHook(download_id)],
            'no_warnings': False,  # Enable warnings for debugging
            'extract_flat': False,
            'socket_timeout': 15,
            'retries': 1,  # Reduce retries to fail faster
            'fragment_retries': 1,
            'ignoreerrors': False,
            'verbose': True,  # Enable verbose output for debugging
            'quiet': False,
            # Add user agent to avoid blocking
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
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
        
        logging.info(f"STEP 7: Starting yt-dlp download with options: {ydl_opts}")
        
        # Update progress to show download starting
        update_progress(download_id, {
            'status': 'starting',
            'message': 'Starting yt-dlp download...'
        })
        logging.info(f"STEP 8: Set starting status for {download_id}")
        
        logging.info(f"STEP 9: About to start download thread for {download_id}")
        download_success = False
        error_message = None
        
        def download_worker():
            nonlocal download_success, error_message
            try:
                logging.info(f"Download worker starting for {download_id}")
                
                # First, test if we can extract info without downloading
                try:
                    logging.info(f"Testing URL extraction for {download_id}")
                    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as test_ydl:
                        info = test_ydl.extract_info(url, download=False)
                        logging.info(f"URL extraction successful for {download_id}: {info.get('title', 'Unknown')[:50]}")
                except Exception as extract_error:
                    logging.error(f"URL extraction failed for {download_id}: {extract_error}")
                    raise Exception(f"Failed to extract video info: {extract_error}")
                
                # Now proceed with actual download
                logging.info(f"Starting actual download for {download_id}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logging.info(f"Calling yt-dlp download for {download_id}")
                    ydl.download([url])
                    logging.info(f"yt-dlp download completed for {download_id}")
                
                download_success = True
            except Exception as e:
                error_message = str(e)
                logging.error(f"Download error for {download_id}: {e}")
        
        # Start download in a separate thread with timeout
        import concurrent.futures
        
        logging.info(f"Starting download thread for {download_id}")
        
        # Update progress to show we're actively downloading
        update_progress(download_id, {
            'status': 'downloading',
            'percent': '0%',
            'speed': 'Starting download...',
            'message': 'Download in progress'
        })
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(download_worker)
            
            # Monitor progress with periodic updates
            import time
            start_time = time.time()
            
            while True:
                try:
                    # Check if download is complete every 3 seconds
                    future.result(timeout=3)
                    # Download completed successfully
                    logging.info(f"Download thread completed for {download_id}, success: {download_success}")
                    
                    # Immediately update to show we're past the download phase
                    download_progress[download_id] = {
                        'status': 'downloading',
                        'percent': '100%',
                        'speed': 'Completed',
                        'message': 'Download finished'
                    }
                    break
                    
                except concurrent.futures.TimeoutError:
                    # Still downloading, update progress periodically
                    elapsed = time.time() - start_time
                    if elapsed > 180:  # 3 minute total timeout
                        logging.error(f"Download timed out after 3 minutes for {download_id}")
                        download_progress[download_id] = {
                            'status': 'error',
                            'error': 'Download timed out after 3 minutes'
                        }
                        return
                    
                    # Update progress based on elapsed time (simulation)
                    if elapsed < 60:  # First minute: 0-70%
                        percent = min(int((elapsed / 60) * 70), 70)
                    else:  # After first minute: 70-95%
                        percent = min(70 + int(((elapsed - 60) / 120) * 25), 95)
                    
                    download_progress[download_id] = {
                        'status': 'downloading',
                        'percent': f'{percent}%',
                        'speed': 'Downloading...',
                        'message': 'Download in progress'
                    }
                    continue
            
        
        if error_message:
            download_progress[download_id] = {
                'status': 'error',
                'error': error_message
            }
            return
        
        if not download_success:
            download_progress[download_id] = {
                'status': 'error',
                'error': 'Download failed for unknown reason'
            }
            return
            
        # Update progress to show processing
        download_progress[download_id] = {
            'status': 'processing',
            'message': 'Download completed, processing files...'
        }
        
        logging.info(f"Download completed, checking files in {downloads_dir}")
        
        # List all files in the directory for debugging
        all_files = list(downloads_dir.iterdir()) if downloads_dir.exists() else []
        logging.info(f"Files found in directory: {[f.name for f in all_files if f.is_file()]}")
        
        # Initialize user downloads if needed
        if user_id not in user_downloads:
            user_downloads[user_id] = []
            logging.info(f"Created new user downloads list for {user_id}")
        
        # Initialize files list to track what gets added to user downloads
        final_files = []
        logging.info(f"Starting file processing for format_type: {format_type}, ffmpeg_working: {ffmpeg_working}, PYDUB_AVAILABLE: {PYDUB_AVAILABLE}")
        
        try:
            # Post-process for MP3 conversion if needed
            if format_type == 'mp3' and not ffmpeg_working and PYDUB_AVAILABLE:
                logging.info("Starting custom MP3 conversion...")
                # Update progress to show conversion
                download_progress[download_id] = {
                    'status': 'converting',
                    'message': 'Converting to MP3...'
                }
                
                # Process audio files for conversion
                for file_path in downloads_dir.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in ['.webm', '.m4a', '.ogg']:
                        mp3_path = file_path.with_suffix('.mp3')
                        logging.info(f"Converting {file_path.name} to {mp3_path.name}")
                        
                        if convert_to_mp3(file_path, mp3_path):
                            # Conversion successful - remove original and track MP3
                            file_path.unlink()
                            logging.info(f"Successfully converted to MP3: {mp3_path.name}")
                            final_files.append(mp3_path)
                        else:
                            logging.warning(f"Conversion failed, keeping original: {file_path.name}")
                            final_files.append(file_path)
                
                # Add a small delay to ensure file operations are complete
                import time
                time.sleep(1)
                
                logging.info(f"MP3 conversion completed for {download_id}")
            else:
                # For non-MP3 downloads or when FFmpeg is working, add all files normally
                for file_path in downloads_dir.iterdir():
                    if file_path.is_file():
                        final_files.append(file_path)
            
            # Add final files to user's list
            logging.info(f"Processing {len(final_files)} final files for user downloads")
            for file_path in final_files:
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
                        logging.info(f"Added file to user downloads: {file_path.name}")
                    else:
                        logging.info(f"File already exists in user downloads: {file_path.name}")
                else:
                    logging.warning(f"File does not exist: {file_path}")
            
            # Final delay to ensure all file operations are complete
            import time
            time.sleep(0.5)
            
            # Now set the final status after all files have been processed
            download_progress[download_id] = {
                'status': 'finished',
                'message': 'Download completed successfully!'
            }
            logging.info(f"Set final status to finished for {download_id} after processing {len(final_files)} files")
                        
        except Exception as conv_error:
            logging.error(f"Error in post-processing: {conv_error}")
            download_progress[download_id] = {
                'status': 'error',
                'error': f'Post-processing failed: {str(conv_error)}'
            }
        
        logging.info(f"Download {download_id} completed successfully - files in user list: {len(user_downloads.get(user_id, []))}")
            
    except Exception as e:
        logging.error(f"Download {download_id} failed: {str(e)}")
        download_progress[download_id] = {
            'status': 'error',
            'error': str(e)
        }

@app.route('/progress/<download_id>')
def get_progress(download_id):
    # Clean up old progress data periodically
    cleanup_old_progress()
    
    progress = download_progress.get(download_id, {'status': 'not_found'})
    
    # Only log if it's not a repeated 'not_found' to reduce log spam
    if progress['status'] != 'not_found':
        logging.info(f"Progress requested for {download_id}: {progress}")
    
    response = jsonify(progress)
    # Add headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

@app.route('/downloads')
def list_downloads():
    # Ensure user has session
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        user_downloads[session['user_id']] = []
        logging.info(f"Downloads endpoint: Created new session with user_id: {session['user_id']}")
    
    user_id = session['user_id']
    logging.info(f"========== DOWNLOADS ENDPOINT DEBUG ===========")
    logging.info(f"Downloads endpoint: Listing downloads for user_id: {user_id}")
    logging.info(f"Downloads endpoint: Available user_downloads keys: {list(user_downloads.keys())}")
    logging.info(f"Downloads endpoint: Files in memory for this user: {user_downloads.get(user_id, 'NOT_FOUND')}")
    logging.info(f"Downloads endpoint: Request headers: {dict(request.headers)}")
    logging.info(f"Downloads endpoint: Session data: {dict(session)}")
    
    # Get user's downloads from memory first
    if user_id in user_downloads:
        files = user_downloads[user_id].copy()
    else:
        files = []
        user_downloads[user_id] = []
    
    # Also check user's directory for any files, but filter out intermediate files
    user_downloads_dir = Path('downloads') / user_id
    logging.info(f"Downloads endpoint: Checking directory: {user_downloads_dir}")
    logging.info(f"Downloads endpoint: Directory exists: {user_downloads_dir.exists()}")
    
    if user_downloads_dir.exists():
        all_files_on_disk = list(user_downloads_dir.iterdir())
        logging.info(f"Downloads endpoint: All files on disk: {[f.name for f in all_files_on_disk if f.is_file()]}")
        
        for file_path in user_downloads_dir.iterdir():
            if file_path.is_file():
                logging.info(f"Downloads endpoint: Processing file: {file_path.name}")
                # Skip webm/m4a files if an MP3 version exists (they're intermediate files)
                if file_path.suffix.lower() in ['.webm', '.m4a', '.ogg']:
                    mp3_version = file_path.with_suffix('.mp3')
                    if mp3_version.exists():
                        logging.info(f"Skipping {file_path.name} because MP3 version exists")
                        continue
                
                file_info = {
                    'name': file_path.name,
                    'size': file_path.stat().st_size,
                    'modified': file_path.stat().st_mtime
                }
                logging.info(f"Downloads endpoint: Adding file to list: {file_info}")
                # Avoid duplicates
                if not any(f['name'] == file_info['name'] for f in files):
                    files.append(file_info)
                    logging.info(f"Downloads endpoint: File added successfully")
                else:
                    logging.info(f"Downloads endpoint: File already exists in list, skipping")
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    
    logging.info(f"Returning {len(files)} files for user {user_id}: {[f['name'] for f in files]}")
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
    try:
        port = int(os.environ.get('PORT', 8080))
        logging.info(f"Starting Flask app on port {port}")
        app.run(debug=False, host='0.0.0.0', port=port)
    except Exception as e:
        logging.error(f"Failed to start Flask app: {e}")
        raise
