# Add this to your app.py for more efficient transcription

import io
import concurrent.futures
from functools import partial

@app.route('/transcribe-url-optimized', methods=['POST'])
def transcribe_url_optimized():
    """
    Optimized transcription that minimizes memory usage and maximizes speed
    """
    try:
        data = request.json
        url = data.get('url')
        language = data.get('language', 'auto')
        
        # Step 1: Extract audio URL directly without downloading
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Find best audio format (prefer opus/webm for efficiency)
            best_audio = None
            for fmt in info.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    # Prefer opus codec for smaller size
                    if 'opus' in fmt.get('acodec', ''):
                        best_audio = fmt
                        break
                    elif not best_audio:
                        best_audio = fmt
            
            if not best_audio:
                return jsonify({'error': 'No audio stream found'}), 400
            
            audio_url = best_audio['url']
            duration = info.get('duration', 0)
        
        # Step 2: Stream and process audio in chunks
        # For SenseVoice (server-side)
        if language in ['zh', 'zh-CN', 'zh-TW', 'yue', 'ja', 'ko'] and SENSEVOICE_AVAILABLE:
            # Use ffmpeg to stream directly to SenseVoice
            import subprocess
            
            # Stream audio with ffmpeg
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', audio_url,
                '-f', 'wav',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-'  # Output to pipe
            ]
            
            # Process with chunked streaming
            chunk_size = 16000 * 30  # 30-second chunks
            transcripts = []
            
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            
            # Read and process chunks
            while True:
                chunk = process.stdout.read(chunk_size * 2)  # 16-bit audio
                if not chunk:
                    break
                
                # Convert to numpy array
                audio_chunk = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Transcribe chunk with SenseVoice
                if len(audio_chunk) > 16000:  # At least 1 second
                    result = sensevoice_model.transcribe(audio_chunk, language=language)
                    transcripts.append(result['text'])
            
            process.wait()
            
            return jsonify({
                'success': True,
                'transcript': ' '.join(transcripts),
                'model': 'SenseVoice',
                'language': language,
                'duration': duration
            })
            
        else:
            # For Whisper (client-side), we need to provide audio data
            # Option 1: Stream audio data to client in chunks
            # Option 2: Provide direct audio URL for client-side processing
            
            return jsonify({
                'success': True,
                'audio_url': audio_url,  # Let client handle streaming
                'duration': duration,
                'codec': best_audio.get('acodec'),
                'size': best_audio.get('filesize', 0),
                'message': 'Process audio client-side with Whisper'
            })
            
    except Exception as e:
        logging.error(f"Optimized transcription error: {e}")
        return jsonify({'error': str(e)}), 500


# Add WebSocket support for real-time streaming transcription
from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('transcribe_stream')
def handle_transcribe_stream(data):
    """
    WebSocket endpoint for real-time streaming transcription
    """
    url = data.get('url')
    language = data.get('language', 'auto')
    
    def stream_transcribe():
        # Get audio stream URL
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = None
            
            for fmt in info.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_url = fmt['url']
                    break
        
        if not audio_url:
            emit('error', {'message': 'No audio stream found'})
            return
        
        # Stream with ffmpeg
        import subprocess
        ffmpeg_cmd = [
            'ffmpeg', '-i', audio_url,
            '-f', 'wav', '-ar', '16000', '-ac', '1', '-'
        ]
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        
        chunk_size = 16000 * 10  # 10-second chunks
        chunk_num = 0
        
        while True:
            chunk = process.stdout.read(chunk_size * 2)
            if not chunk:
                break
            
            # Convert and transcribe
            audio_chunk = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
            
            if len(audio_chunk) > 16000:
                # Transcribe (using appropriate model)
                transcript = "Chunk {} transcribed".format(chunk_num)  # Replace with actual
                
                # Emit result
                emit('transcript_chunk', {
                    'chunk': chunk_num,
                    'text': transcript,
                    'timestamp': chunk_num * 10
                })
                
                chunk_num += 1
        
        emit('transcription_complete', {'total_chunks': chunk_num})
    
    # Run in background thread
    from threading import Thread
    thread = Thread(target=stream_transcribe)
    thread.start()
