#!/usr/bin/env python3

"""
SenseVoice transcription integration for Flask app
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SenseVoiceTranscriber:
    """SenseVoice transcription wrapper"""
    
    def __init__(self):
        self.model = None
        self.is_available = False
        self._initialize()
    
    def _initialize(self):
        """Initialize SenseVoice model"""
        try:
            from funasr import AutoModel
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            
            logger.info("Loading SenseVoice model...")
            model_dir = "iic/SenseVoiceSmall"
            
            # Load model with simplified settings for MP3 support
            self.model = AutoModel(
                model=model_dir,
                trust_remote_code=True,
                device="cpu",  # Use CPU for stability
                disable_update=True,  # Skip version checks
                disable_log=False     # Enable logging to debug
            )
            
            self.rich_transcription_postprocess = rich_transcription_postprocess
            self.is_available = True
            logger.info(f"✅ SenseVoice model loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize SenseVoice: {e}")
            self.is_available = False
    
def transcribe(self, audio_file_path: str, language: str = "auto") -> Dict[str, Any]:
        """
        Transcribe audio file using SenseVoice
        
        Args:
            audio_file_path: Path to audio file
            language: Language code ("auto", "zh", "en", "yue", "ja", "ko")
            
        Returns:
            Dictionary with transcription results
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "SenseVoice is not available",
                "text": ""
            }
        
        if not os.path.exists(audio_file_path):
            return {
                "success": False,
                "error": f"Audio file not found: {audio_file_path}",
                "text": ""
            }
        
        try:
            logger.info(f"🎤 Transcribing: {Path(audio_file_path).name}")
            logger.info(f"📊 Language: {language}")
            logger.info(f"📁 File size: {os.path.getsize(audio_file_path) / (1024*1024):.2f} MB")
            
            # Process audio in segments
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_file_path)

            total_duration = len(audio) / 1000
            segment_duration = 15  # 15 seconds
            full_transcription = ""

            for start_time in range(0, int(total_duration), segment_duration):
                end_time = min(start_time + segment_duration, total_duration)
                segment = audio[start_time * 1000:end_time * 1000]

                segment.export("temp_segment.wav", format="wav")
                logger.info(f"Processing segment: {start_time} to {end_time} seconds")

                segment_transcription = self.transcribe_segment("temp_segment.wav", language)

                full_transcription += segment_transcription + "\n"

            return {
                "success": True,
                "text": full_transcription.strip(),
                "raw_text": full_transcription.strip(),
                "language": language,
                "file_path": audio_file_path
            }

    def transcribe_segment(self, segment_path: str, language: str):
        res = self.model.generate(
                input=audio_file_path,
                cache={},
                language=language if language != "auto" else None,  # Let model auto-detect if "auto"
                use_itn=True,         # Include punctuation
                batch_size_s=20,       # Process according to segment size
                merge_vad=True
            )
            
            if res and len(res) > 0:
                # Post-process the transcription
                raw_text = res[0]["text"]
                processed_text = self.rich_transcription_postprocess(raw_text)
                
                logger.info(f"✅ Transcription completed successfully")
                logger.info(f"📝 Text length: {len(processed_text)} characters")
                
return raw_text.strip()
            else:
                logger.warning("⚠️ Transcription returned empty result")
return ""
        except Exception as e:
            logger.error(f"❌ Transcription segment failed: {e}")
            return ""
                
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            return {
                "success": False,
                "error": f"Transcription error: {str(e)}",
                "text": ""
            }
    
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
                "Emotion Recognition", 
                "Audio Event Detection",
                "Fast Inference (15x faster than Whisper-Large)"
            ]
        }

# Create global transcriber instance
sense_voice_transcriber = SenseVoiceTranscriber()

def is_sensevoice_available() -> bool:
    """Check if SenseVoice is available"""
    return sense_voice_transcriber.is_available

def transcribe_with_sensevoice(audio_file_path: str, language: str = "auto") -> Dict[str, Any]:
    """
    Convenience function for transcription
    
    Args:
        audio_file_path: Path to audio file
        language: Language code
        
    Returns:
        Transcription results dictionary
    """
    return sense_voice_transcriber.transcribe(audio_file_path, language)

def get_sensevoice_status() -> Dict[str, Any]:
    """Get SenseVoice status"""
    return sense_voice_transcriber.get_status()
