from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_babel import Babel, gettext, get_locale
import yt_dlp
import os
import re
import time
import uuid
import logging
import threading
from pathlib import Path
from resource_manager import ResourceManager

# Import SenseVoice transcription
try:
    from sensevoice_transcription import (
        is_sensevoice_available,
        transcribe_with_sensevoice,
        transcribe_with_sensevoice_streaming,
        transcribe_with_sensevoice_from_array,
        get_sensevoice_status
    )
    SENSEVOICE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"SenseVoice not available: {e}")
    SENSEVOICE_AVAILABLE = False

# Import Whisper transcription
from whisper_transcription import (
    is_whisper_available,
    transcribe_from_url_with_whisper,
    transcribe_from_url_streaming_whisper_generator,
    WhisperTranscriber,
    get_whisper_status
)
WHISPER_AVAILABLE = True

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

# Initialize resource manager
try:
    resource_manager = ResourceManager(app)
except ImportError as e:
    logging.warning(f"Resource manager not available (missing psutil): {e}")
    resource_manager = None

# Configure Babel
babel = Babel()
babel.init_app(app)
app.config['LANGUAGES'] = {
    'en': 'English',
    'es': 'Español', 
    'zh': '中文'
}
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_DEFAULT_TIMEZONE'] = 'UTC'

def get_locale():
    # 1. Check if user explicitly selected a language
    if 'language' in session:
        return session['language']
    # 2. Try to guess the language from the user accept header
    return request.accept_languages.best_match(app.config['LANGUAGES'].keys()) or 'en'

babel.init_app(app, locale_selector=get_locale)

# Make get_locale available in templates
@app.context_processor
def inject_conf_vars():
    return {'get_locale': get_locale}

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
    """Clean up progress data older than 30 minutes"""
    import time
    current_time = time.time()
    old_keys = []
    
    for download_id, timestamp in progress_timestamps.items():
        if current_time - timestamp > 1800:  # 30 minutes
            old_keys.append(download_id)
    
    for key in old_keys:
        download_progress.pop(key, None)
        progress_timestamps.pop(key, None)
        logging.info(f"Cleaned up old progress data for download {key}")

def strip_ansi_codes(text):
    """Remove ANSI color codes from text"""
    if not isinstance(text, str):
        return text
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text).strip()

def sanitize_filename(filename, max_length=100):
    """Sanitize and truncate filename to avoid filesystem issues while preserving readability"""
    if not filename:
        return "video"
    
    # Step 1: Preserve the original filename by keeping alphanumeric, spaces, and common punctuation
    # Only replace truly problematic filesystem characters
    filename = str(filename)  # Ensure it's a string
    
    # Replace filesystem-dangerous characters with safer alternatives
    replacements = {
        '<': '(',
        '>': ')',
        ':': '-',
        '"': "'",
        '/': '-',
        '\\': '-',
        '|': '-',
        '?': '',
        '*': '',
        '\x00': '',  # null character
    }
    
    for bad_char, replacement in replacements.items():
        filename = filename.replace(bad_char, replacement)
    
    # Step 2: Clean up multiple spaces, dashes, and dots but preserve structure
    filename = re.sub(r'\s+', ' ', filename)  # Multiple spaces to single space
    filename = re.sub(r'-+', '-', filename)   # Multiple dashes to single dash
    filename = re.sub(r'\.-', '.', filename)  # Remove dash after dot
    filename = re.sub(r'-\.', '.', filename)  # Remove dash before dot
    
    # Step 3: Remove leading/trailing problematic characters but keep content
    filename = filename.strip(' .-_')
    
    # Step 4: Truncate to max length but try to break at word boundaries
    if len(filename) > max_length:
        # Try to truncate at a space to avoid breaking words
        truncated = filename[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.8:  # If space is reasonably close to end
            filename = truncated[:last_space]
        else:
            filename = truncated
        
        # Clean up the end after truncation
        filename = filename.rstrip(' .-_')
    
    # Step 5: Final safety check - ensure we have something meaningful
    if not filename or len(filename) < 3:
        filename = "video"
    
    return filename

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
                # Clean up percent and speed strings by removing ANSI color codes
                percent_raw = d.get('_percent_str', 'N/A')
                speed_raw = d.get('_speed_str', 'N/A')
                
                percent = strip_ansi_codes(percent_raw)
                speed = strip_ansi_codes(speed_raw)
                
                download_progress[self.download_id] = {
                    'status': 'downloading',
                    'percent': percent,
                    'speed': speed
                }
                logging.info(f"Progress {self.download_id}: {percent} at {speed}")
            elif d['status'] == 'finished':
                # Don't set 'finished' yet - let the main download function handle final status
                # after post-processing (MP3 conversion) is complete
                download_progress[self.download_id] = {
                    'status': 'processing',
                    'message': 'Download completed, processing files...'
                }
                logging.info(f"Download {self.download_id} finished downloading: {d.get('filename', 'unknown')}, moving to processing")
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
    
    return render_template('index.html', languages=app.config['LANGUAGES'])

@app.route('/set_language/<language>')
def set_language(language=None):
    if language in app.config['LANGUAGES']:
        session['language'] = language
    return redirect(request.referrer or url_for('index'))

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
    
    response_data = {
        'active_downloads': len(download_progress),
        'download_progress': download_progress,
        'user_downloads_count': len(user_downloads),
        'current_user_id': current_user_id,
        'user_downloads_in_memory': user_downloads.get(current_user_id, []),
        'files_on_disk': files_on_disk,
        'all_user_downloads': user_downloads
    }
    
    # Add resource manager stats if available
    if resource_manager:
        stats = resource_manager.get_system_stats()
        if stats:
            response_data['system_stats'] = stats
    
    return jsonify(response_data)

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
        format_type = data.get('format', 'video')  # 'video', 'mp3', or 'transcribe'
        
        # Convert 'transcribe' format to 'mp3' since we need audio for transcription
        if format_type == 'transcribe':
            format_type = 'mp3'
            logging.info(f"Transcribe format requested, converting to MP3 download")
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Ensure user has session
        if 'user_id' not in session:
            session['user_id'] = str(uuid.uuid4())
            user_downloads[session['user_id']] = []
            logging.info(f"Download endpoint: Created new session with user_id: {session['user_id']}")
        
        user_id = session['user_id']
        logging.info(f"Download endpoint: Using user_id: {user_id}")
        
        # Check resource limits if resource manager is available
        if resource_manager:
            if not resource_manager.can_start_download(user_id):
                return jsonify({'error': 'Too many concurrent downloads. Please wait for current downloads to finish.'}), 429
            
            if not resource_manager.check_disk_space():
                return jsonify({'error': 'Server storage is full. Please try again later.'}), 503
        
        # Generate unique download ID
        download_id = str(int(time.time() * 1000))
        
        original_format = data.get('format', 'video')
        logging.info(f"Starting download for URL: {url}, original format: {original_format}, actual format: {format_type}")
        
        # Track download start with resource manager
        if resource_manager:
            resource_manager.start_download(user_id)
        
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
        
        # Configure yt-dlp options with cleaner output
        # First get video info to check title length
        video_title = None
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as test_ydl:
                info = test_ydl.extract_info(url, download=False)
                video_title = info.get('title', 'video')
                logging.info(f"Video title: {video_title}")
        except Exception as e:
            logging.warning(f"Could not extract title: {e}")
            video_title = 'video'
        
        # Smart filename template based on byte length (for cross-platform compatibility)
        def get_byte_length(text):
            """Get the UTF-8 byte length of a string"""
            return len(text.encode('utf-8'))
        
        def truncate_to_bytes(text, max_bytes=180):
            """Truncate text to fit within max_bytes UTF-8 bytes, preserving word boundaries"""
            if get_byte_length(text) <= max_bytes:
                return text
            
            # Binary search to find the longest substring that fits
            left, right = 0, len(text)
            best_length = 0
            
            while left <= right:
                mid = (left + right) // 2
                if get_byte_length(text[:mid]) <= max_bytes:
                    best_length = mid
                    left = mid + 1
                else:
                    right = mid - 1
            
            truncated = text[:best_length]
            
            # Try to break at word boundary
            if best_length < len(text) and best_length > max_bytes * 0.8:
                last_space = truncated.rfind(' ')
                if last_space > max_bytes * 0.7:  # Only if reasonably close
                    truncated = truncated[:last_space]
            
            return truncated.rstrip(' .-_')
        
        title_bytes = get_byte_length(video_title)
        logging.info(f"Video title '{video_title[:50]}...' is {len(video_title)} chars, {title_bytes} bytes")
        
        # Use byte-aware truncation (leaving room for .mp3/.mp4 extension)
        if title_bytes > 180:  # Conservative limit, accounting for extension
            truncated_title = truncate_to_bytes(video_title, 180)
            # Create a custom template with the pre-truncated title
            safe_title = truncated_title.replace('%', '%%')  # Escape any % in title
            filename_template = f'{safe_title}.%(ext)s'
            logging.info(f"Using byte-truncated title: '{truncated_title}' ({get_byte_length(truncated_title)} bytes)")
        else:
            filename_template = '%(title)s.%(ext)s'
            logging.info(f"Using full title ({title_bytes} bytes - safe for all filesystems)")
        
        base_opts = {
            'outtmpl': {'default': str(downloads_dir / filename_template)},
            'restrictfilenames': False,  # Keep original titles readable
            'windowsfilenames': False,   # Don't over-restrict filenames
            'progress_hooks': [ProgressHook(download_id)],
            'no_warnings': False,
            'extract_flat': False,
            'socket_timeout': 15,
            'retries': 1,
            'fragment_retries': 1,
            'ignoreerrors': False,
            'verbose': True,
            'quiet': False,
            # Add user agent to avoid blocking
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate'
            },
            # Reduce color output for better parsing
            'compat_opts': set(),
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
                logging.info(f"Using filename template: {ydl_opts['outtmpl']['default']}")
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        logging.info(f"Calling yt-dlp download for {download_id}")
                        ydl.download([url])
                        logging.info(f"yt-dlp download completed for {download_id}")
                except Exception as download_error:
                    error_str = str(download_error)
                    logging.error(f"Download error for {download_id}: {download_error}")
                    
                    # Check VERY specifically for filename too long errors
                    is_filename_too_long = (
                        "[Errno 36]" in error_str and "File name too long" in error_str
                    ) or (
                        "[Errno 63]" in error_str  # Another filename too long error code
                    ) or (
                        "filename too long" in error_str.lower() and "errno" in error_str.lower()
                    )
                    
                    if is_filename_too_long:
                        logging.warning(f"CONFIRMED filename too long error detected. Retrying with video ID for {download_id}")
                        logging.warning(f"Original filename error: {download_error}")
                        
                        # Retry with video ID as filename (guaranteed to be short)
                        fallback_opts = ydl_opts.copy()
                        fallback_opts['outtmpl'] = {'default': str(downloads_dir / '%(id)s.%(ext)s')}
                        
                        logging.info(f"Retrying download with video ID template: {fallback_opts['outtmpl']['default']}")
                        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                            ydl.download([url])
                            logging.info(f"SUCCESS: Download completed with video ID fallback for {download_id}")
                    else:
                        # Not a filename error - re-raise the original error
                        logging.error(f"Not a filename length error - re-raising: {download_error}")
                        raise download_error
                
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
                    
                    # Update to show we're moving to processing phase
                    download_progress[download_id] = {
                        'status': 'processing',
                        'message': 'Download completed, processing files...'
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
    finally:
        # Always mark download as finished in resource manager
        if resource_manager:
            resource_manager.finish_download(user_id)

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

@app.route('/sensevoice-status')
def sensevoice_status():
    """Get SenseVoice transcription status"""
    if not SENSEVOICE_AVAILABLE:
        return jsonify({
            'available': False,
            'error': 'SenseVoice not installed or not working'
        })
    
    try:
        status = get_sensevoice_status()
        return jsonify(status)
    except Exception as e:
        logging.error(f"Error getting SenseVoice status: {e}")
        return jsonify({
            'available': False,
            'error': f'SenseVoice error: {str(e)}'
        })

@app.route('/whisper-status')
def whisper_status():
    """Get Whisper transcription status"""
    if not WHISPER_AVAILABLE:
        return jsonify({
            'available': False,
            'error': 'Whisper not installed or not working'
        })
    
    try:
        status = get_whisper_status()
        return jsonify(status)
    except Exception as e:
        logging.error(f"Error getting Whisper status: {e}")
        return jsonify({
            'available': False,
            'error': f'Whisper error: {str(e)}'
        })

@app.route('/test-dependencies')
def test_dependencies():
    """Test endpoint to check dependencies"""
    import sys
    
    results = {
        'python_version': sys.version,
        'dependencies': {}
    }
    
    # Test imports
    dependencies = [
        "funasr",
        "torch",
        "torchaudio",
        "librosa",
        "soundfile",
        "numpy",
        "scipy"
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
            results['dependencies'][dep] = 'OK'
        except ImportError as e:
            results['dependencies'][dep] = f'FAILED: {str(e)}'
    
    # Test SenseVoice initialization
    try:
        from funasr import AutoModel
        results['funasr_automodel'] = 'OK'
    except Exception as e:
        results['funasr_automodel'] = f'FAILED: {str(e)}'
    
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        results['funasr_postprocess'] = 'OK'
    except Exception as e:
        results['funasr_postprocess'] = f'FAILED: {str(e)}'
    
    return jsonify(results)

@app.route('/transcribe-url-poll', methods=['POST'])
def transcribe_url_poll():
    """Polling-based transcription for environments that don't support SSE"""
    try:
        data = request.json
        url = data.get('url')
        language = data.get('language', 'auto')
        session_id = data.get('session_id')  # For tracking progress
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Start transcription in background thread
        def background_transcription():
            # Store progress in a shared dict
            transcription_progress = {
                'status': 'initializing',
                'chunks': [],
                'final_transcript': '',
                'error': None,
                'complete': False
            }
            download_progress[f'transcribe_{session_id}'] = transcription_progress
            
            try:
                # Your existing transcription logic here, but update progress dict
                # instead of yielding SSE events
                logging.info(f"Starting transcription for session {session_id}")
                
                # Similar logic to transcribe_url but updates progress dict
                # This is a simplified version - you'd adapt your full logic
                transcription_progress['status'] = 'processing'
                transcription_progress['complete'] = True
                transcription_progress['final_transcript'] = 'Transcription complete'
                
            except Exception as e:
                transcription_progress['error'] = str(e)
                transcription_progress['complete'] = True
        
        # Start background thread
        thread = threading.Thread(target=background_transcription)
        thread.daemon = True
        thread.start()
        
        return jsonify({'session_id': session_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/transcribe-progress/<session_id>')
def get_transcribe_progress(session_id):
    """Get transcription progress for polling"""
    progress_key = f'transcribe_{session_id}'
    progress = download_progress.get(progress_key, {'status': 'not_found'})
    return jsonify(progress)

@app.route('/transcribe-url', methods=['POST', 'GET'])
def transcribe_url():
    """Transcribe audio directly from YouTube URL with optimized streaming"""
    try:
        # Handle both POST and GET for streaming support
        if request.method == 'GET':
            url = request.args.get('url')
            language = request.args.get('language', 'auto')
            streaming = request.args.get('streaming', 'false').lower() == 'true'
        else:
            data = request.json
            url = data.get('url')
            language = data.get('language', 'auto')
            streaming = data.get('streaming', False)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Ensure user has session
        if 'user_id' not in session:
            session['user_id'] = str(uuid.uuid4())
            user_downloads[session['user_id']] = []
        
        user_id = session['user_id']
        logging.info(f"Starting optimized URL transcription for user {user_id}: {url}")
        
        # Check if SenseVoice is available
        if not SENSEVOICE_AVAILABLE:
            return jsonify({
                'error': 'SenseVoice transcription service is not available. Please try again later.'
            }), 503
        
        # Define languages that SenseVoice handles well
        sensevoice_optimal_languages = ['zh', 'zh-CN', 'zh-TW', 'yue', 'ja', 'ko']
        
        # Use Whisper for non-Asian languages (including when auto detection)
        # For auto mode, we'll determine which model to use after detecting the language
        if WHISPER_AVAILABLE and language != 'auto' and language not in sensevoice_optimal_languages:
            logging.info(f"Using Whisper for transcription (language: {language})")
            
            # If streaming is requested, return SSE
            if streaming:
                def generate_whisper_streaming_response():
                    import json
                    try:
                        for chunk in transcribe_from_url_streaming_whisper_generator(url, language):
                            yield f"data: {json.dumps(chunk)}\n\n"
                    except Exception as e:
                        error_data = {
                            'success': False,
                            'error': str(e),
                            'final': True
                        }
                        yield f"data: {json.dumps(error_data)}\n\n"
                
                from flask import Response
                return Response(
                    generate_whisper_streaming_response(),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'Access-Control-Allow-Origin': '*'
                    }
                )
            else:
                # Non-streaming mode - still use streaming internally to avoid download
                result = transcribe_from_url_with_whisper(url, language, streaming=True)
                
                if result.get('success'):
                    return jsonify(result)
                else:
                    # Fallback to SenseVoice if Whisper fails
                    logging.warning(f"Whisper failed: {result.get('error')}, falling back to SenseVoice")
        
        # For explicit non-Asian languages without Whisper, tell user to use client-side
        if not WHISPER_AVAILABLE and language != 'auto' and language not in sensevoice_optimal_languages:
            return jsonify({
                'error': 'For this language, please download the audio file first to use client-side Whisper transcription.',
                'suggested_action': 'download_first'
            }), 400
        
        # Extract direct audio stream URL from YouTube
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        logging.info(f"Extracting audio stream URL from: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            
            # Find best audio format (prefer higher quality for transcription)
            best_audio = None
            audio_formats = []
            
            # Collect all audio-only formats
            for fmt in info.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_formats.append(fmt)
            
            # Sort by audio bitrate (higher is better) for quality
            audio_formats.sort(key=lambda f: f.get('abr', 0) or 0, reverse=True)
            
            # Try to find best quality format (prefer m4a/mp4 for compatibility, then opus/webm)
            for codec_preference in ['mp4a', 'm4a', 'opus', 'vorbis']:
                for fmt in audio_formats:
                    if codec_preference in fmt.get('acodec', ''):
                        best_audio = fmt
                        break
                if best_audio:
                    break
            
            # If no preferred codec found, just use highest bitrate
            if not best_audio and audio_formats:
                best_audio = audio_formats[0]
            
            if not best_audio:
                return jsonify({'error': 'No audio stream found'}), 400
            
            audio_url = best_audio['url']
            logging.info(f"Found audio stream: {best_audio.get('acodec')} at {best_audio.get('abr', 'unknown')} kbps")
        
        # Use ffmpeg to stream directly to SenseVoice
        import subprocess
        import numpy as np
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', audio_url,
            '-f', 'wav',
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            '-'
        ]
        
        # If streaming is requested, return Server-Sent Events
        if streaming:
            # Check if we're on Railway (which doesn't support SSE well)
            is_railway = os.environ.get('RAILWAY_ENVIRONMENT') is not None
            
            def generate_streaming_response():
                import json
                
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                
                # Process with chunked streaming
                chunk_size = 16000 * 30  # 30-second chunks
                chunk_count = 0
                total_transcript = []
                detected_language = None
                
                # Initialize variables for language detection
                use_language = language if language != 'auto' else None
                detected_language = None
                whisper_transcriber = None
                
                # Initialize Whisper if available for auto detection
                if language == 'auto' and WHISPER_AVAILABLE:
                    try:
                        whisper_transcriber = WhisperTranscriber(model_size="base")
                        logging.info("Auto language detection requested, will use Whisper to detect from first chunk")
                    except Exception as e:
                        logging.warning(f"Failed to initialize Whisper: {e}")
                        use_language = 'zh'  # Fallback to Chinese for SenseVoice
                
                try:
                    while True:
                        chunk = process.stdout.read(chunk_size * 2)  # 2 bytes per sample
                        if not chunk:
                            break
                        
                        # Convert to numpy array
                        audio_chunk = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                        
                        # Transcribe chunk if it's long enough (at least 1 second)
                        if len(audio_chunk) > 16000:
                            chunk_count += 1
                            logging.info(f"Transcribing chunk {chunk_count} ({len(audio_chunk)/16000:.1f}s)")
                            
                            # Detect language from first chunk if auto mode
                            if chunk_count == 1 and language == 'auto' and whisper_transcriber:
                                try:
                                    detected_language = whisper_transcriber.detect_language(audio_chunk)
                                    logging.info(f"Detected language: {detected_language}")
                                    
                                    # Decide which model to use based on detected language
                                    if detected_language in sensevoice_optimal_languages:
                                        use_language = detected_language
                                        logging.info(f"Using SenseVoice for {detected_language}")
                                    else:
                                        # Use Whisper for non-Asian languages
                                        result = whisper_transcriber.transcribe(audio_chunk, language=detected_language)
                                        if result.get('success'):
                                            text = result['text'].strip()
                                            if text and len(text) > 1:
                                                total_transcript.append(text)
                                                chunk_data = {
                                                    'success': True,
                                                    'text': text,
                                                    'chunk': chunk_count,
                                                    'model': 'whisper',
                                                    'language': detected_language,
                                                    'final': False
                                                }
                                                yield f"data: {json.dumps(chunk_data)}\n\n"
                                        continue  # Skip SenseVoice processing
                                except Exception as e:
                                    logging.warning(f"Language detection failed: {e}, defaulting to Chinese")
                                    use_language = 'zh'
                                    detected_language = 'zh'
                            
                            # Use appropriate transcription based on language
                            if detected_language and detected_language not in sensevoice_optimal_languages and whisper_transcriber:
                                # Use Whisper for non-Asian languages
                                result = whisper_transcriber.transcribe(audio_chunk, language=detected_language)
                                model_used = 'whisper'
                            else:
                                # Use SenseVoice for Asian languages or fallback
                                result = transcribe_with_sensevoice_from_array(
                                    audio_array=audio_chunk,
                                    sample_rate=16000,
                                    language=use_language or 'zh',
                                    model_name='SenseVoiceSmall'
                                )
                                model_used = 'sensevoice'
                            
                            if result.get('success') and result.get('text'):
                                # Filter out empty or very short transcripts
                                text = result['text'].strip()
                                if text and len(text) > 1:  # Skip single character results
                                    total_transcript.append(text)
                                    
                                    # Send chunk data via SSE
                                    chunk_data = {
                                        'success': True,
                                        'text': text,
                                        'chunk': chunk_count,
                                        'final': False
                                    }
                                    yield f"data: {json.dumps(chunk_data)}\n\n"
                                    logging.info(f"Chunk {chunk_count} sent: {len(text)} chars")
                    
                    process.wait()
                    
                    # Send final result
                    # Determine which model was predominantly used
                    final_model = 'SenseVoice'
                    if detected_language and detected_language not in sensevoice_optimal_languages:
                        final_model = 'Whisper'
                    
                    final_data = {
                        'success': True,
                        'transcript': ' '.join(total_transcript),
                        'model': final_model,
                        'language': detected_language or use_language,
                        'duration': duration,
                        'title': video_title,
                        'chunks_processed': chunk_count,
                        'final': True
                    }
                    yield f"data: {json.dumps(final_data)}\n\n"
                    
                except Exception as e:
                    process.terminate()
                    error_data = {
                        'success': False,
                        'error': f'Streaming error: {str(e)}',
                        'final': True
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
            
            from flask import Response
            return Response(
                generate_streaming_response(),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Access-Control-Allow-Origin': '*'
                }
            )
        
        # Non-streaming mode (original implementation)
        logging.info("Starting ffmpeg streaming process")
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        
        # Process with chunked streaming
        chunk_size = 16000 * 30  # 30-second chunks
        transcripts = []
        chunk_count = 0
        detected_language = None  # For auto language detection
        
        # If language is 'auto', we need to detect it from the first chunk
        # by saving to a temporary file
        if language == 'auto':
            logging.info("Language set to 'auto', will detect from first chunk")
        
        try:
            while True:
                chunk = process.stdout.read(chunk_size * 2)  # 2 bytes per sample
                if not chunk:
                    break
                
                # Convert to numpy array
                audio_chunk = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Transcribe chunk if it's long enough (at least 1 second)
                if len(audio_chunk) > 16000:
                    chunk_count += 1
                    logging.info(f"Transcribing chunk {chunk_count} ({len(audio_chunk)/16000:.1f}s)")
                    
                    # For auto language detection, default to Chinese since SenseVoice is optimized for Asian languages
                    if language == 'auto':
                        use_language = 'zh'  # Default to Chinese for auto mode
                        if chunk_count == 1:
                            logging.info("Auto language detection requested, defaulting to Chinese (zh) for SenseVoice")
                    else:
                        use_language = language
                    
                    # Always use the specific language for array transcription
                    result = transcribe_with_sensevoice_from_array(
                        audio_array=audio_chunk,
                        sample_rate=16000,
                        language=use_language,
                        model_name='SenseVoiceSmall'
                    )
                    
                    if result.get('success') and result.get('text'):
                        # Filter out empty or very short transcripts
                        text = result['text'].strip()
                        if text and len(text) > 1:  # Skip single character results
                            transcripts.append(text)
                            logging.info(f"Chunk {chunk_count} transcribed successfully: {len(text)} chars")
                        else:
                            logging.info(f"Chunk {chunk_count} returned empty/short text, skipping")
                    else:
                        logging.warning(f"Chunk {chunk_count} transcription failed: {result.get('error')}")
            
            process.wait()
            
            if process.returncode != 0:
                logging.warning(f"FFmpeg process ended with return code: {process.returncode}")
            
            # Combine all transcripts
            full_transcript = ' '.join(transcripts)
            
            logging.info(f"Transcription completed: {chunk_count} chunks processed")
            
            return jsonify({
                'success': True,
                'transcript': full_transcript,
                'model': 'SenseVoice',
                'language': detected_language if detected_language else language,
                'duration': duration,
                'title': video_title,
                'chunks_processed': chunk_count
            })
            
        except Exception as e:
            process.terminate()
            raise e
            
    except Exception as e:
        logging.error(f"Optimized URL transcription error: {e}")
        return jsonify({'error': f'Transcription failed: {str(e)}'}), 500

@app.route('/transcribe', methods=['GET', 'POST'])
def transcribe_audio():
    """Transcribe audio file using SenseVoice with streaming support"""
    try:
        # Check if SenseVoice is available
        if not SENSEVOICE_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'SenseVoice is not available'
            }), 400
        
        # Ensure user has session
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Handle GET request for Server-Sent Events
        if request.method == 'GET':
            filename = request.args.get('filename')
            language = request.args.get('language', 'auto')
            model_name = request.args.get('model', 'SenseVoiceSmall')
            streaming = request.args.get('streaming', 'false').lower() == 'true'
        else:
            # Handle POST request (legacy)
            data = request.json
            filename = data.get('filename')
            language = data.get('language', 'auto')
            model_name = data.get('model', 'SenseVoiceSmall')  # Default to small model
            streaming = data.get('streaming', False)  # Support both streaming and non-streaming
        
        if not filename:
            return jsonify({
                'success': False,
                'error': 'Filename is required'
            }), 400
        
        user_id = session['user_id']
        user_downloads_dir = Path('downloads') / user_id
        audio_file_path = user_downloads_dir / filename
        
        # Check if file exists
        if not audio_file_path.exists():
            return jsonify({
                'success': False,
                'error': f'Audio file not found: {filename}'
            }), 404
        
        # Check if file is audio format
        if not audio_file_path.suffix.lower() in ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.webm']:
            return jsonify({
                'success': False,
                'error': f'Unsupported audio format: {audio_file_path.suffix}'
            }), 400
        
        logging.info(f"🎤 Starting transcription for {filename} (language: {language}, model: {model_name}, streaming: {streaming})")
        
        if streaming:
            # Return streaming response
            def generate_streaming_response():
                try:
                    for chunk in transcribe_with_sensevoice_streaming(str(audio_file_path), language, model_name):
                        # Convert to JSON string for SSE
                        import json
                        yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as e:
                    error_chunk = {
                        'success': False,
                        'error': f'Streaming transcription error: {str(e)}',
                        'final': True
                    }
                    import json
                    yield f"data: {json.dumps(error_chunk)}\n\n"
            
            from flask import Response
            return Response(
                generate_streaming_response(),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Access-Control-Allow-Origin': '*'
                }
            )
        else:
            # Non-streaming transcription (legacy support)
            result = transcribe_with_sensevoice(str(audio_file_path), language, model_name)
            logging.info(f"📝 Transcription completed: success={result.get('success', False)}")
            return jsonify(result)
        
    except Exception as e:
        logging.error(f"Transcription endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

if __name__ == '__main__':
    import os
    try:
        port = int(os.environ.get('PORT', 8080))
        logging.info(f"Starting Flask app on port {port}")
        app.run(debug=False, host='0.0.0.0', port=port)
    except Exception as e:
        logging.error(f"Failed to start Flask app: {e}")
        raise
