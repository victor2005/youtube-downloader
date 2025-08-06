"""
Whisper transcription module for multi-language audio transcription
Uses local Whisper models (open-source)
"""

import logging
import numpy as np
from typing import Optional, Dict, Any, Generator
import subprocess
import tempfile
import os

# Import Whisper
import whisper
WHISPER_AVAILABLE = True



class WhisperTranscriber:
    """Whisper transcription with automatic language detection and multi-language support"""
    
    def __init__(self, model_size: str = "base", use_gpu: bool = True):
        """
        Initialize Whisper transcriber
        
        Args:
            model_size: One of 'tiny', 'base', 'small', 'medium', 'large'
            use_gpu: Whether to use GPU if available
        """
        self.model_size = model_size
        self.use_gpu = use_gpu
        self.model = None
        self.device = None
        
        if WHISPER_AVAILABLE:
            self._load_model()
    
    def _load_model(self):
        """Load Whisper model"""
        try:
            import torch
            
            # Determine device
            if self.use_gpu and torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
            
            # Check if we should use cached model directory from Docker build
            whisper_cache = os.environ.get('WHISPER_CACHE_DIR')
            if whisper_cache:
                logging.info(f"Using Whisper cache directory: {whisper_cache}")
                # Load model with explicit download_root to use Docker cached models
                logging.info(f"Loading Whisper model '{self.model_size}' from {whisper_cache} on {self.device}")
                self.model = whisper.load_model(self.model_size, device=self.device, download_root=whisper_cache)
            else:
                logging.info(f"Loading Whisper model '{self.model_size}' on {self.device}")
                self.model = whisper.load_model(self.model_size, device=self.device)
            logging.info("Whisper model loaded successfully")
            
        except Exception as e:
            logging.error(f"Failed to load Whisper model: {e}")
            self.model = None
    
    def detect_language(self, audio_array: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Detect language from audio
        
        Args:
            audio_array: Audio data as numpy array
            sample_rate: Sample rate of audio
            
        Returns:
            Detected language code (e.g., 'en', 'zh', 'es')
        """
        if not self.model:
            return "en"  # Default fallback
        
        try:
            # Ensure audio is float32 and correct sample rate
            if audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)
            
            # Detect language using first 30 seconds
            audio_segment = audio_array[:30 * sample_rate]
            
            # Pad if too short
            if len(audio_segment) < sample_rate:
                audio_segment = np.pad(audio_segment, (0, sample_rate - len(audio_segment)))
            
            # Detect language
            audio_segment = whisper.pad_or_trim(audio_segment)
            mel = whisper.log_mel_spectrogram(audio_segment).to(self.device)
            
            _, probs = self.model.detect_language(mel)
            detected_lang = max(probs, key=probs.get)
            
            logging.info(f"Detected language: {detected_lang} (confidence: {probs[detected_lang]:.2f})")
            
            # Log top 3 languages
            top_langs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
            logging.info(f"Top language predictions: {top_langs}")
            
            return detected_lang
            
        except Exception as e:
            logging.error(f"Language detection failed: {e}")
            return "en"
    
    def transcribe(self, 
                   audio_array: np.ndarray, 
                   language: Optional[str] = None,
                   sample_rate: int = 16000,
                   task: str = "transcribe") -> Dict[str, Any]:
        """
        Transcribe audio using Whisper
        
        Args:
            audio_array: Audio data as numpy array
            language: Language code or None for auto-detection
            sample_rate: Sample rate of audio
            task: 'transcribe' or 'translate' (to English)
            
        Returns:
            Transcription result with text, language, and segments
        """
        if not self.model:
            return {
                'success': False,
                'error': 'Whisper model not loaded'
            }
        
        try:
            # Ensure audio is float32
            if audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)
            
            # Auto-detect language if not specified
            if language == "auto" or language is None:
                language = self.detect_language(audio_array, sample_rate)
            
            logging.info(f"Transcribing with Whisper (language: {language}, task: {task})")
            
            # Transcribe
            result = self.model.transcribe(
                audio_array,
                language=language,
                task=task,
                fp16=self.device == "cuda",  # Use FP16 on GPU
                verbose=False
            )
            
            return {
                'success': True,
                'text': result['text'].strip(),
                'language': result.get('language', language),
                'segments': result.get('segments', []),
                'model': f'whisper-{self.model_size}'
            }
            
        except Exception as e:
            logging.error(f"Whisper transcription failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def transcribe_streaming(self,
                           audio_stream: Generator[np.ndarray, None, None],
                           language: Optional[str] = None,
                           chunk_length: int = 30) -> Generator[Dict[str, Any], None, None]:
        """
        Transcribe audio stream in chunks
        
        Args:
            audio_stream: Generator yielding audio chunks
            language: Language code or None for auto-detection
            chunk_length: Length of each chunk in seconds
            
        Yields:
            Transcription results for each chunk
        """
        detected_language = None
        chunk_number = 0
        
        for audio_chunk in audio_stream:
            chunk_number += 1
            
            # Detect language from first chunk if needed
            if chunk_number == 1 and (language == "auto" or language is None):
                detected_language = self.detect_language(audio_chunk)
            
            # Use detected or specified language
            use_language = detected_language if detected_language else language
            
            # Transcribe chunk
            result = self.transcribe(audio_chunk, language=use_language)
            
            if result['success']:
                yield {
                    'chunk': chunk_number,
                    'text': result['text'],
                    'language': result['language'],
                    'timestamp': (chunk_number - 1) * chunk_length,
                    'final': False
                }


def transcribe_from_url_with_whisper(url: str, language: str = "auto", streaming: bool = False, preloaded_transcriber: Optional['WhisperTranscriber'] = None) -> Dict[str, Any]:
    """
    Transcribe audio from URL using Whisper with automatic language detection
    Can either download to temp file or stream directly
    
    Args:
        url: YouTube or direct audio URL
        language: Language code or "auto" for detection
        streaming: If True, stream audio without downloading full file
        preloaded_transcriber: Optional pre-loaded WhisperTranscriber instance
        
    Returns:
        Transcription result
    """
    if streaming:
        return transcribe_from_url_streaming_whisper(url, language, preloaded_transcriber)
    else:
        # Original download-based approach for non-streaming
        temp_file = None
        try:
            import yt_dlp
            import uuid
            
            # Use pre-loaded transcriber if available, otherwise create new one
            transcriber = preloaded_transcriber if preloaded_transcriber else WhisperTranscriber(model_size="base")
            
            # Create temporary directory if it doesn't exist
            temp_dir = tempfile.gettempdir()
            os.makedirs(os.path.join(temp_dir, 'whisper_temp'), exist_ok=True)
            
            # Generate unique filename
            temp_filename = os.path.join(temp_dir, 'whisper_temp', f'audio_{uuid.uuid4().hex}.mp3')
            
            # Configure yt-dlp to download audio
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_filename,
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            # Download audio
            logging.info(f"Downloading audio to temporary file: {temp_filename}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
            
            # Find the actual downloaded file (yt-dlp might change the extension)
            temp_file = temp_filename
            if not os.path.exists(temp_file):
                # Check for common audio extensions
                for ext in ['.mp3', '.m4a', '.opus', '.webm', '.wav']:
                    check_file = temp_filename.rsplit('.', 1)[0] + ext
                    if os.path.exists(check_file):
                        temp_file = check_file
                        break
            
            if not os.path.exists(temp_file):
                return {'success': False, 'error': 'Failed to download audio file'}
            
            logging.info(f"Audio downloaded successfully to: {temp_file}")
            
            # Load audio file
            audio_array = whisper.load_audio(temp_file)
            
            # Transcribe with auto language detection
            result = transcriber.transcribe(audio_array, language=language)
            
            if result['success']:
                return {
                    'success': True,
                    'transcript': result['text'],
                    'language': result['language'],
                    'model': result['model'],
                    'title': video_title,
                    'duration': duration
                }
            else:
                return result
                
        except Exception as e:
            logging.error(f"Whisper URL transcription failed: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logging.info(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logging.warning(f"Failed to clean up temporary file: {e}")


def transcribe_from_url_streaming_whisper_generator(url: str, language: str = "auto", preloaded_transcriber: Optional['WhisperTranscriber'] = None) -> Generator[Dict[str, Any], None, None]:
    """
    Stream audio from URL and transcribe with Whisper in chunks
    Yields SSE-compatible chunks for real-time streaming
    
    Args:
        url: YouTube or direct audio URL
        language: Language code or "auto" for detection
        preloaded_transcriber: Optional pre-loaded WhisperTranscriber instance
        
    Yields:
        Dict chunks for SSE streaming
    """
    try:
        import yt_dlp
        
        # Use pre-loaded transcriber if available, otherwise create new one
        transcriber = preloaded_transcriber if preloaded_transcriber else WhisperTranscriber(model_size="base")
        
        # Extract audio stream URL
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            
            # Find best audio format
            best_audio = None
            audio_formats = []
            
            for fmt in info.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_formats.append(fmt)
            
            # Sort by bitrate for quality
            audio_formats.sort(key=lambda f: f.get('abr', 0) or 0, reverse=True)
            
            # Prefer formats that work well with streaming
            for codec_preference in ['mp4a', 'm4a', 'opus', 'vorbis']:
                for fmt in audio_formats:
                    if codec_preference in fmt.get('acodec', ''):
                        best_audio = fmt
                        break
                if best_audio:
                    break
            
            if not best_audio and audio_formats:
                best_audio = audio_formats[0]
            
            if not best_audio:
                yield {'success': False, 'error': 'No audio stream found', 'final': True}
                return
            
            audio_url = best_audio['url']
            logging.info(f"Found audio stream: {best_audio.get('acodec')} at {best_audio.get('abr', 'unknown')} kbps")
        
        # Stream audio with ffmpeg
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', audio_url,
            '-f', 'wav',
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            '-'
        ]
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL  # Discard stderr to prevent buffer filling up
        )
        
        # Process audio with natural pause detection
        transcripts = []
        detected_language = None
        chunk_count = 0
        
        # Audio buffer for accumulating segments
        audio_buffer = []
        silence_threshold = 0.01  # Adjust based on testing
        min_silence_duration = 0.5  # 0.5 seconds of silence
        max_segment_duration = 30  # Maximum 30 seconds per segment
        min_segment_duration = 1  # Minimum 1 second per segment
        
        sample_rate = 16000
        silence_samples = int(min_silence_duration * sample_rate)
        max_samples = int(max_segment_duration * sample_rate)
        min_samples = int(min_segment_duration * sample_rate)
        
        consecutive_silence = 0
        segment_start_time = 0
        
        logging.info("Starting streaming transcription with Whisper using natural pause detection")
        
        try:
            while True:
                # Read small chunks for better pause detection
                chunk_data = process.stdout.read(1600 * 2)  # 0.1 second chunks
                if not chunk_data:
                    # Process any remaining audio
                    if audio_buffer and len(audio_buffer) >= min_samples:
                        audio_segment = np.array(audio_buffer)
                        chunk_count += 1
                        
                        # Detect language from first chunk if auto
                        if chunk_count == 1 and language == 'auto':
                            detected_language = transcriber.detect_language(audio_segment)
                            logging.info(f"Detected language: {detected_language}")
                        
                        use_language = detected_language if detected_language else language
                        result = transcriber.transcribe(audio_segment, language=use_language if use_language != 'auto' else None)
                        
                        if result.get('success') and result.get('text'):
                            text = result['text'].strip()
                            if text:
                                transcripts.append(text)
                                # Yield chunk
                                yield {
                                    'success': True,
                                    'text': text,
                                    'chunk': chunk_count,
                                    'language': detected_language or language,
                                    'model': f'whisper-{transcriber.model_size}',
                                    'final': False
                                }
                    break
                
                # Convert to numpy array
                audio_chunk = np.frombuffer(chunk_data, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Add to buffer
                audio_buffer.extend(audio_chunk)
                
                # Check for silence
                chunk_energy = np.mean(np.abs(audio_chunk))
                if chunk_energy < silence_threshold:
                    consecutive_silence += len(audio_chunk)
                else:
                    consecutive_silence = 0
                
                # Check if we should process a segment
                should_process = False
                current_duration = len(audio_buffer) / sample_rate
                
                if consecutive_silence >= silence_samples and len(audio_buffer) >= min_samples:
                    # Natural pause detected
                    should_process = True
                    logging.info(f"Natural pause detected at {current_duration:.1f}s")
                elif len(audio_buffer) >= max_samples:
                    # Maximum duration reached
                    should_process = True
                    logging.info(f"Maximum segment duration reached at {current_duration:.1f}s")
                
                if should_process:
                    # Process segment
                    audio_segment = np.array(audio_buffer)
                    chunk_count += 1
                    
                    # Detect language from first chunk if auto
                    if chunk_count == 1 and language == 'auto':
                        detected_language = transcriber.detect_language(audio_segment)
                        logging.info(f"Detected language: {detected_language}")
                    
                    # Use detected language or specified language
                    use_language = detected_language if detected_language else language
                    
                    # Transcribe chunk
                    logging.info(f"Processing segment {chunk_count} ({len(audio_segment)/sample_rate:.1f}s)")
                    result = transcriber.transcribe(audio_segment, language=use_language if use_language != 'auto' else None)
                    
                    if result.get('success') and result.get('text'):
                        text = result['text'].strip()
                        if text:  # Only add non-empty text
                            transcripts.append(text)
                            # Yield chunk for SSE
                            yield {
                                'success': True,
                                'text': text,
                                'chunk': chunk_count,
                                'language': detected_language or language,
                                'model': f'whisper-{transcriber.model_size}',
                                'final': False
                            }
                    
                    # Reset buffer and counters
                    audio_buffer = []
                    consecutive_silence = 0
                    segment_start_time += current_duration
            
            # Wait for process to finish
            process.wait()
            
            # Yield final result
            full_transcript = ' '.join(transcripts)
            yield {
                'success': True,
                'transcript': full_transcript,
                'language': detected_language if detected_language else language,
                'model': f'whisper-{transcriber.model_size}',
                'title': video_title,
                'duration': duration,
                'chunks_processed': chunk_count,
                'final': True
            }
            
        except Exception as e:
            logging.error(f"Streaming transcription error: {e}")
            process.terminate()
            yield {'success': False, 'error': f'Streaming transcription failed: {str(e)}', 'final': True}
        finally:
            # Ensure process is terminated
            if process.poll() is None:
                process.terminate()
                
    except Exception as e:
        logging.error(f"Whisper streaming setup failed: {e}")
        yield {'success': False, 'error': str(e), 'final': True}


def transcribe_from_url_streaming_whisper(url: str, language: str = "auto", preloaded_transcriber: Optional['WhisperTranscriber'] = None) -> Dict[str, Any]:
    """
    Stream audio from URL and transcribe with Whisper in chunks
    Uses VAD for natural pause detection
    
    Args:
        url: YouTube or direct audio URL
        language: Language code or "auto" for detection
        preloaded_transcriber: Optional pre-loaded WhisperTranscriber instance
        
    Returns:
        Transcription result
    """
    try:
        import yt_dlp
        
        # Use pre-loaded transcriber if available, otherwise create new one
        transcriber = preloaded_transcriber if preloaded_transcriber else WhisperTranscriber(model_size="base")
        
        # Extract audio stream URL
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            
            # Find best audio format
            best_audio = None
            audio_formats = []
            
            for fmt in info.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_formats.append(fmt)
            
            # Sort by bitrate for quality
            audio_formats.sort(key=lambda f: f.get('abr', 0) or 0, reverse=True)
            
            # Prefer formats that work well with streaming
            for codec_preference in ['mp4a', 'm4a', 'opus', 'vorbis']:
                for fmt in audio_formats:
                    if codec_preference in fmt.get('acodec', ''):
                        best_audio = fmt
                        break
                if best_audio:
                    break
            
            if not best_audio and audio_formats:
                best_audio = audio_formats[0]
            
            if not best_audio:
                return {'success': False, 'error': 'No audio stream found'}
            
            audio_url = best_audio['url']
            logging.info(f"Found audio stream: {best_audio.get('acodec')} at {best_audio.get('abr', 'unknown')} kbps")
        
        # Stream audio with ffmpeg
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', audio_url,
            '-f', 'wav',
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            '-'
        ]
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL  # Discard stderr to prevent buffer filling up
        )
        
        # Process audio with natural pause detection
        transcripts = []
        detected_language = None
        chunk_count = 0
        
        # Audio buffer for accumulating segments
        audio_buffer = []
        silence_threshold = 0.01  # Adjust based on testing
        min_silence_duration = 0.5  # 0.5 seconds of silence
        max_segment_duration = 30  # Maximum 30 seconds per segment
        min_segment_duration = 1  # Minimum 1 second per segment
        
        sample_rate = 16000
        silence_samples = int(min_silence_duration * sample_rate)
        max_samples = int(max_segment_duration * sample_rate)
        min_samples = int(min_segment_duration * sample_rate)
        
        consecutive_silence = 0
        segment_start_time = 0
        
        logging.info("Starting streaming transcription with Whisper using natural pause detection")
        
        try:
            while True:
                # Read small chunks for better pause detection
                chunk_data = process.stdout.read(1600 * 2)  # 0.1 second chunks
                if not chunk_data:
                    # Process any remaining audio
                    if audio_buffer and len(audio_buffer) >= min_samples:
                        audio_segment = np.array(audio_buffer)
                        chunk_count += 1
                        
                        # Detect language from first chunk if auto
                        if chunk_count == 1 and language == 'auto':
                            detected_language = transcriber.detect_language(audio_segment)
                            logging.info(f"Detected language: {detected_language}")
                        
                        use_language = detected_language if detected_language else language
                        result = transcriber.transcribe(audio_segment, language=use_language if use_language != 'auto' else None)
                        
                        if result.get('success') and result.get('text'):
                            text = result['text'].strip()
                            if text:
                                transcripts.append(text)
                                logging.info(f"Final chunk {chunk_count} transcribed: {len(text)} chars")
                    break
                
                # Convert to numpy array
                audio_chunk = np.frombuffer(chunk_data, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Add to buffer
                audio_buffer.extend(audio_chunk)
                
                # Check for silence
                chunk_energy = np.mean(np.abs(audio_chunk))
                if chunk_energy < silence_threshold:
                    consecutive_silence += len(audio_chunk)
                else:
                    consecutive_silence = 0
                
                # Check if we should process a segment
                should_process = False
                current_duration = len(audio_buffer) / sample_rate
                
                if consecutive_silence >= silence_samples and len(audio_buffer) >= min_samples:
                    # Natural pause detected
                    should_process = True
                    logging.info(f"Natural pause detected at {current_duration:.1f}s")
                elif len(audio_buffer) >= max_samples:
                    # Maximum duration reached
                    should_process = True
                    logging.info(f"Maximum segment duration reached at {current_duration:.1f}s")
                
                if should_process:
                    # Process segment
                    audio_segment = np.array(audio_buffer)
                    chunk_count += 1
                    
                    # Detect language from first chunk if auto
                    if chunk_count == 1 and language == 'auto':
                        detected_language = transcriber.detect_language(audio_segment)
                        logging.info(f"Detected language: {detected_language}")
                    
                    # Use detected language or specified language
                    use_language = detected_language if detected_language else language
                    
                    # Transcribe chunk
                    logging.info(f"Processing segment {chunk_count} ({len(audio_segment)/sample_rate:.1f}s)")
                    result = transcriber.transcribe(audio_segment, language=use_language if use_language != 'auto' else None)
                    
                    if result.get('success') and result.get('text'):
                        text = result['text'].strip()
                        if text:  # Only add non-empty text
                            transcripts.append(text)
                            logging.info(f"Segment {chunk_count} transcribed: {len(text)} chars")
                    
                    # Reset buffer and counters
                    audio_buffer = []
                    consecutive_silence = 0
                    segment_start_time += current_duration
            
            # Wait for process to finish
            process.wait()
            
            # Check for errors
            if process.returncode != 0:
                stderr = process.stderr.read().decode('utf-8', errors='ignore')
                if stderr:
                    logging.warning(f"FFmpeg stderr: {stderr}")
            
            # Combine all transcripts
            full_transcript = ' '.join(transcripts)
            
            return {
                'success': True,
                'transcript': full_transcript,
                'language': detected_language if detected_language else language,
                'model': f'whisper-{transcriber.model_size}',
                'title': video_title,
                'duration': duration,
                'chunks_processed': chunk_count
            }
            
        except Exception as e:
            logging.error(f"Streaming transcription error: {e}")
            process.terminate()
            return {'success': False, 'error': f'Streaming transcription failed: {str(e)}'}
        finally:
            # Ensure process is terminated
            if process.poll() is None:
                process.terminate()
                
    except Exception as e:
        logging.error(f"Whisper streaming setup failed: {e}")
        return {'success': False, 'error': str(e)}


# Helper functions for Flask integration
def is_whisper_available() -> bool:
    """Check if Whisper is available"""
    return WHISPER_AVAILABLE

def get_whisper_status() -> Dict[str, Any]:
    """Get Whisper status and available models"""
    if not WHISPER_AVAILABLE:
        return {
            'available': False,
            'error': 'Whisper not installed'
        }
    
    try:
        import torch
        
        return {
            'available': True,
            'models': ['tiny', 'base', 'small', 'medium', 'large'],
            'gpu_available': torch.cuda.is_available(),
            'device': 'cuda' if torch.cuda.is_available() else 'cpu'
        }
    except Exception as e:
        return {
            'available': False,
            'error': str(e)
        }
