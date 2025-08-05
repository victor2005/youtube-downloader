#!/usr/bin/env python3

"""
SenseVoice transcription integration with natural pause detection and streaming
Similar to Whisper approach - chunks by natural pauses and streams results
"""

# Suppress FunASR's verbose table output BEFORE importing
import os
os.environ['FUNASR_LOG_LEVEL'] = 'ERROR'

import logging
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Generator
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress FunASR internal loggers
logging.getLogger('funasr').setLevel(logging.ERROR)
logging.getLogger('funasr.register').setLevel(logging.ERROR)
logging.getLogger('funasr.utils').setLevel(logging.ERROR)
logging.getLogger('funasr.models').setLevel(logging.ERROR)
logging.getLogger('funasr.auto').setLevel(logging.ERROR)

class SenseVoiceTranscriber:
    """SenseVoice transcription wrapper with natural pause detection and model selection"""
    
    def __init__(self):
        self.models = {}  # Cache multiple models
        self.current_model_name = None
        self.is_available = False
        self.rich_transcription_postprocess = None
        self._initialize_postprocess()
    
    def _initialize_postprocess(self):
        """Initialize post-processing utilities"""
        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            self.rich_transcription_postprocess = rich_transcription_postprocess
            self.is_available = True
            logger.info("✅ SenseVoice post-processing initialized")
        except Exception as e:
            import traceback
            logger.error(f"❌ Failed to initialize SenseVoice post-processing: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.is_available = False
    
    def _get_model_config(self, model_name="SenseVoiceSmall"):
        """Get model configuration based on model name"""
        configs = {
            "SenseVoiceSmall": {
                "model_dir": "iic/SenseVoiceSmall",
                "description": "Fast and lightweight model"
            },
            "SenseVoice": {
                "model_dir": "iic/SenseVoice", 
                "description": "Standard quality model"
            },
            "SenseVoiceLarge": {
                "model_dir": "iic/SenseVoiceLarge",
                "description": "High quality model (slower)"
            }
        }
        return configs.get(model_name, configs["SenseVoiceSmall"])
    
    def _load_model(self, model_name="SenseVoiceSmall"):
        """Load specific SenseVoice model"""
        try:
            from funasr import AutoModel
            
            config = self._get_model_config(model_name)
            model_dir = config["model_dir"]
            
            logger.info(f"Loading {model_name} model ({config['description']})...")
            
            # Load model with optimized settings
            model = AutoModel(
                model=model_dir,
                trust_remote_code=True,
                device="cpu",
                disable_update=True,
                disable_log=True  # Disable FunASR's verbose logging
            )
            
            self.models[model_name] = model
            self.current_model_name = model_name
            logger.info(f"✅ {model_name} model loaded successfully")
            return model
            
        except Exception as e:
            logger.error(f"❌ Failed to load {model_name} model: {e}")
            return None
    
    def get_model(self, model_name="SenseVoiceSmall"):
        """Get or load a specific model"""
        if model_name not in self.models:
            model = self._load_model(model_name)
            if model is None:
                return None
        return self.models[model_name]
    
    def find_speech_segments(self, audio_file_path: str, base_chunk_duration: int = 30) -> List[Tuple[int, int]]:
        """
        Find natural pauses in audio using energy-based detection
        Similar to Whisper's approach but adapted for SenseVoice
        
        Args:
            audio_file_path: Path to audio file
            base_chunk_duration: Base chunk duration in seconds
            
        Returns:
            List of (start_ms, end_ms) tuples for each segment
        """
        try:
            import librosa
            import numpy as np
            
            logger.info("🔍 Detecting natural pauses using energy-based method...")
            
            # Load audio at 16kHz for consistent processing
            y, sr = librosa.load(audio_file_path, sr=16000)
            duration_seconds = len(y) / sr
            
            # Use simple energy-based segmentation
            hop_length = int(0.01 * sr)  # 10ms hop
            frame_length = int(0.03 * sr)  # 30ms frame
            
            # Calculate RMS energy
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            
            # Find silent regions (below 1% of max energy)
            silence_threshold = np.max(rms) * 0.01
            is_silent = rms < silence_threshold
            
            # Convert to time boundaries
            boundaries = []
            start_time = 0
            max_chunk_duration = base_chunk_duration
            
            for i in range(1, len(is_silent)):
                current_time = i * hop_length / sr
                
                # Look for silence transitions or max chunk duration
                if (not is_silent[i-1] and is_silent[i] and current_time - start_time > 5) or \
                   (current_time - start_time >= max_chunk_duration):
                    # Found a pause or reached max duration
                    boundaries.append((int(start_time * 1000), int(current_time * 1000)))
                    start_time = current_time
            
            # Add final segment
            if start_time < duration_seconds:
                boundaries.append((int(start_time * 1000), int(duration_seconds * 1000)))
            
            # If no good boundaries found, use fixed chunks
            if len(boundaries) == 0:
                chunk_ms = base_chunk_duration * 1000
                duration_ms = int(duration_seconds * 1000)
                boundaries = [(start, min(start + chunk_ms, duration_ms)) 
                             for start in range(0, duration_ms, chunk_ms)]
            
            logger.info(f"📊 Detected {len(boundaries)} segments using natural pauses")
            return boundaries
            
        except Exception as e:
            logger.warning(f"Natural pause detection failed, using fixed chunks: {e}")
            # Fallback to fixed-size chunks
            return self._create_fixed_chunks(audio_file_path, base_chunk_duration * 1000)
    
    def _create_fixed_chunks(self, audio_file_path: str, chunk_duration: int = 30000) -> List[Tuple[int, int]]:
        """Create fixed-size chunks as fallback"""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_file_path)
            duration = len(audio)
            
            chunks = []
            for start in range(0, duration, chunk_duration):
                end = min(start + chunk_duration, duration)
                chunks.append((start, end))
            
            return chunks
        except:
            return [(0, 300000)]  # Default 5-minute chunk
    
    def transcribe_streaming(self, audio_file_path: str, language: str = "auto", model_name: str = "SenseVoiceSmall") -> Generator[Dict[str, Any], None, None]:
        """
        Transcribe audio file using SenseVoice with streaming results
        
        Args:
            audio_file_path: Path to audio file
            language: Language code ("auto", "zh", "en", "yue", "ja", "ko")
            model_name: Model to use for transcription
            
        Yields:
            Dictionary with segment transcription results
        """
        if not self.is_available:
            yield {
                "success": False,
                "error": "SenseVoice is not available",
                "text": ""
            }
            return
        
        if not os.path.exists(audio_file_path):
            yield {
                "success": False,
                "error": f"Audio file not found: {audio_file_path}",
                "text": ""
            }
            return
        
        try:
            logger.info(f"🎤 Transcribing: {Path(audio_file_path).name}")
            logger.info(f"📊 Language: {language}")
            logger.info(f"🤖 Model: {model_name}")
            logger.info(f"📁 File size: {os.path.getsize(audio_file_path) / (1024*1024):.2f} MB")
            
            # Get or load the model
            model = self.get_model(model_name)
            if model is None:
                yield {
                    "success": False,
                    "error": f"Failed to load model: {model_name}",
                    "text": ""
                }
                return
            
            # Find speech segments (fast, without loading full audio)
            segments = self.find_speech_segments(audio_file_path)
            total_segments = len(segments)
            
            for idx, (start_ms, end_ms) in enumerate(segments):
                segment_num = idx + 1
                logger.info(f"🔄 Processing segment {segment_num}/{total_segments} "
                          f"[{start_ms/1000:.1f}s - {end_ms/1000:.1f}s]")
                
                # Create temporary file for segment
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                    tmp_path = tmp_file.name
                
                # Extract segment using ffmpeg (fast)
                import subprocess
                start_time = start_ms / 1000
                duration = (end_ms - start_ms) / 1000
                
                cmd = [
                    'ffmpeg', '-i', audio_file_path,
                    '-ss', str(start_time),
                    '-t', str(duration),
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-y', tmp_path
                ]
                
                subprocess.run(cmd, capture_output=True, check=True)
                
                try:
                    # Transcribe segment
                    start_time = time.time()
                    
                    res = model.generate(
                        input=tmp_path,
                        cache={},
                        language=language if language != "auto" else None,
                        use_itn=True,
                        batch_size_s=30,
                        merge_vad=True
                    )
                    
                    elapsed = time.time() - start_time
                    
                    if res and len(res) > 0:
                        raw_text = res[0]["text"]
                        processed_text = self.rich_transcription_postprocess(raw_text)
                        
                        # Try to extract detected language from result
                        detected_lang = None
                        if isinstance(res[0], dict):
                            # Check for language in result metadata
                            detected_lang = res[0].get('lang', None) or res[0].get('language', None)
                            # Log full result structure for debugging
                            logger.debug(f"Full result structure: {list(res[0].keys())}")
                        
                        # Add timestamp and text
                        timestamp = f"[{self._format_time(start_ms/1000)} - {self._format_time(end_ms/1000)}]"
                        segment_text = f"{timestamp} {processed_text}"
                        
                        logger.info(f"✅ Segment {segment_num} completed in {elapsed:.2f}s")
                        
                        yield {
                            "success": True,
                            "segment_text": segment_text,
                            "segment_num": segment_num,
                            "total_segments": total_segments,
                            "start_time": start_ms / 1000,
                            "end_time": end_ms / 1000,
                            "processing_time": elapsed
                        }
                    else:
                        logger.warning(f"⚠️ Segment {segment_num} returned empty result")
                        yield {
                            "success": False,
                            "segment_text": "",
                            "segment_num": segment_num,
                            "total_segments": total_segments,
                            "start_time": start_ms / 1000,
                            "end_time": end_ms / 1000
                        }
                        
                finally:
                    # Clean up temporary file
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                        
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            import traceback
            traceback.print_exc()
            yield {
                "success": False,
                "error": f"Transcription error: {str(e)}",
                "text": ""
            }
    
    def transcribe(self, audio_file_path: str, language: str = "auto", model_name: str = "SenseVoiceSmall") -> Dict[str, Any]:
        """
        Transcribe audio file using SenseVoice (non-streaming version)
        
        Args:
            audio_file_path: Path to audio file
            language: Language code ("auto", "zh", "en", "yue", "ja", "ko")
            model_name: Model to use for transcription
            
        Returns:
            Dictionary with transcription results
        """
        full_transcript = []
        error = None
        
        # Collect all segments from streaming transcription
        for result in self.transcribe_streaming(audio_file_path, language, model_name):
            if result.get("success") and result.get("segment_text"):
                full_transcript.append(result["segment_text"])
            elif result.get("error"):
                error = result["error"]
                break
        
        if error:
            return {
                "success": False,
                "error": error,
                "text": ""
            }
        
        final_transcript = "\n\n".join(full_transcript)
        
        return {
            "success": True,
            "text": final_transcript,
            "raw_text": final_transcript,
            "language": language,
            "file_path": audio_file_path,
            "num_segments": len(full_transcript)
        }
    
    def transcribe_from_array(self, audio_array, sample_rate: int = 16000, language: str = "zh", model_name: str = "SenseVoiceSmall") -> Dict[str, Any]:
        """
        Transcribe audio from numpy array directly
        
        Args:
            audio_array: Numpy array of audio data (float32, normalized to [-1, 1])
            sample_rate: Sample rate of the audio (default: 16000)
            language: Language code ("zh", "en", "yue", "ja", "ko") - cannot be "auto" for array input
            model_name: Model to use for transcription
            
        Returns:
            Dictionary with transcription results
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "SenseVoice is not available",
                "text": ""
            }
        
        if language == "auto":
            return {
                "success": False,
                "error": "Language detection not supported for array input. Please specify language explicitly.",
                "text": ""
            }
        
        try:
            import numpy as np
            import tempfile
            import soundfile as sf
            
            # Get or load the model
            model = self.get_model(model_name)
            if model is None:
                return {
                    "success": False,
                    "error": f"Failed to load model: {model_name}",
                    "text": ""
                }
            
            logger.info(f"🎤 Transcribing audio array")
            logger.info(f"📊 Language: {language}")
            logger.info(f"🤖 Model: {model_name}")
            logger.info(f"🎵 Sample rate: {sample_rate} Hz")
            logger.info(f"⏱️ Duration: {len(audio_array) / sample_rate:.2f} seconds")
            
            # Ensure audio array is float32 and properly normalized
            if not isinstance(audio_array, np.ndarray):
                audio_array = np.array(audio_array, dtype=np.float32)
            elif audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)
            
            # Clip to ensure values are in [-1, 1] range
            audio_array = np.clip(audio_array, -1.0, 1.0)
            
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                # Write audio data to temporary file
                sf.write(tmp_path, audio_array, sample_rate, subtype='PCM_16')
            
            try:
                # Transcribe using the model
                start_time = time.time()
                
                res = model.generate(
                    input=tmp_path,
                    cache={},
                    language=language,
                    use_itn=True,
                    batch_size_s=30,
                    merge_vad=True
                )
                
                elapsed = time.time() - start_time
                
                if res and len(res) > 0:
                    raw_text = res[0]["text"]
                    processed_text = self.rich_transcription_postprocess(raw_text)
                    
                    logger.info(f"✅ Transcription completed in {elapsed:.2f}s")
                    
                    return {
                        "success": True,
                        "text": processed_text,
                        "raw_text": raw_text,
                        "language": language,
                        "duration": len(audio_array) / sample_rate,
                        "processing_time": elapsed
                    }
                else:
                    return {
                        "success": False,
                        "error": "Model returned empty result",
                        "text": ""
                    }
                    
            finally:
                # Clean up temporary file
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
        except Exception as e:
            logger.error(f"❌ Transcription from array failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"Transcription error: {str(e)}",
                "text": ""
            }
    
    def _format_time(self, seconds: float) -> str:
        """Format time in MM:SS format"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def get_supported_languages(self) -> list:
        """Get list of supported languages"""
        return ["auto", "zh", "en", "yue", "ja", "ko"]
    
    def get_status(self) -> Dict[str, Any]:
        """Get transcriber status"""
        return {
            "available": self.is_available,
            "model_name": "SenseVoice-Small",
            "supported_languages": self.get_supported_languages(),
            "features": [
                "Multilingual ASR",
                "Natural Pause Detection",
                "Emotion Recognition", 
                "Audio Event Detection",
                "Fast Inference",
                "Streaming Results"
            ]
        }

# Create global transcriber instance
sense_voice_transcriber = SenseVoiceTranscriber()

def is_sensevoice_available() -> bool:
    """Check if SenseVoice is available"""
    return sense_voice_transcriber.is_available

def transcribe_with_sensevoice(audio_file_path: str, language: str = "auto", model_name: str = "SenseVoiceSmall") -> Dict[str, Any]:
    """
    Convenience function for transcription
    
    Args:
        audio_file_path: Path to audio file
        language: Language code
        model_name: Model to use for transcription
        
    Returns:
        Transcription results dictionary
    """
    return sense_voice_transcriber.transcribe(audio_file_path, language, model_name)

def transcribe_with_sensevoice_streaming(audio_file_path: str, language: str = "auto", model_name: str = "SenseVoiceSmall") -> Generator[Dict[str, Any], None, None]:
    """
    Convenience function for streaming transcription
    
    Args:
        audio_file_path: Path to audio file
        language: Language code
        model_name: Model to use for transcription
        
    Yields:
        Segment transcription results
    """
    yield from sense_voice_transcriber.transcribe_streaming(audio_file_path, language, model_name)

def transcribe_with_sensevoice_from_array(audio_array, sample_rate: int = 16000, language: str = "zh", model_name: str = "SenseVoiceSmall") -> Dict[str, Any]:
    """
    Convenience function for transcription from numpy array
    
    Args:
        audio_array: Numpy array of audio data (float32, normalized to [-1, 1])
        sample_rate: Sample rate of the audio (default: 16000)
        language: Language code ("zh", "en", "yue", "ja", "ko") - cannot be "auto" for array input
        model_name: Model to use for transcription
        
    Returns:
        Transcription results dictionary
    """
    return sense_voice_transcriber.transcribe_from_array(audio_array, sample_rate, language, model_name)

def get_sensevoice_status() -> Dict[str, Any]:
    """Get SenseVoice status"""
    return sense_voice_transcriber.get_status()
