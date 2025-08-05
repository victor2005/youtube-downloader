#!/usr/bin/env python3

"""
SenseVoice transcription integration with natural pause detection
Similar to Whisper approach - chunks by natural pauses
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SenseVoiceTranscriber:
    """SenseVoice transcription wrapper with natural pause detection"""
    
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
            
            # Load model with optimized settings
            self.model = AutoModel(
                model=model_dir,
                trust_remote_code=True,
                device="cpu",
                disable_update=True,
                disable_log=False
            )
            
            self.rich_transcription_postprocess = rich_transcription_postprocess
            self.is_available = True
            logger.info(f"✅ SenseVoice model loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize SenseVoice: {e}")
            self.is_available = False
    
    def find_speech_segments(self, audio_file_path: str, min_silence_len: int = 1000, 
                           silence_thresh: int = -40) -> List[Tuple[int, int]]:
        """
        Find speech segments based on natural pauses in audio
        
        Args:
            audio_file_path: Path to audio file
            min_silence_len: Minimum length of silence in milliseconds
            silence_thresh: Silence threshold in dB
            
        Returns:
            List of (start_ms, end_ms) tuples for each speech segment
        """
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent
            
            logger.info("🔍 Detecting speech segments...")
            audio = AudioSegment.from_file(audio_file_path)
            
            # Find non-silent chunks
            nonsilent_chunks = detect_nonsilent(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh
            )
            
            # Merge chunks that are too close together
            merged_chunks = []
            if nonsilent_chunks:
                current_start, current_end = nonsilent_chunks[0]
                
                for start, end in nonsilent_chunks[1:]:
                    # If chunks are within 500ms, merge them
                    if start - current_end < 500:
                        current_end = end
                    else:
                        merged_chunks.append((current_start, current_end))
                        current_start, current_end = start, end
                
                merged_chunks.append((current_start, current_end))
            
            # Split very long chunks (over 30 seconds)
            final_chunks = []
            max_chunk_duration = 30000  # 30 seconds in milliseconds
            
            for start, end in merged_chunks:
                duration = end - start
                if duration > max_chunk_duration:
                    # Split into smaller chunks
                    num_splits = int(duration / max_chunk_duration) + 1
                    split_duration = duration / num_splits
                    
                    for i in range(num_splits):
                        split_start = start + int(i * split_duration)
                        split_end = start + int((i + 1) * split_duration)
                        if split_end > end:
                            split_end = end
                        final_chunks.append((split_start, split_end))
                else:
                    final_chunks.append((start, end))
            
            logger.info(f"📊 Found {len(final_chunks)} speech segments")
            return final_chunks
            
        except Exception as e:
            logger.error(f"Failed to detect speech segments: {e}")
            # Fallback to fixed-size chunks
            return self._create_fixed_chunks(audio_file_path)
    
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
    
    def transcribe(self, audio_file_path: str, language: str = "auto") -> Dict[str, Any]:
        """
        Transcribe audio file using SenseVoice with natural pause detection

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
            from pydub import AudioSegment
            import tempfile

            logger.info(f"🎤 Transcribing: {Path(audio_file_path).name}")
            logger.info(f"📊 Language: {language}")
            logger.info(f"📁 File size: {os.path.getsize(audio_file_path) / (1024*1024):.2f} MB")

            # Load audio
            audio = AudioSegment.from_file(audio_file_path)

            # Find speech segments
            segments = self.find_speech_segments(audio_file_path)

            full_transcript = []
            total_segments = len(segments)

            for idx, (start_ms, end_ms) in enumerate(segments):
                segment_num = idx + 1
                logger.info(f"🔄 Processing segment {segment_num}/{total_segments} "
                            f"[{start_ms/1000:.1f}s - {end_ms/1000:.1f}s]")

                # Extract segment
                segment = audio[start_ms:end_ms]

                # Save segment to temporary file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                    segment.export(tmp_file.name, format='wav')
                    tmp_path = tmp_file.name

                try:
                    # Transcribe segment
                    start_time = time.time()

                    res = self.model.generate(
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

                        # Add timestamp and text
                        timestamp = f"[{self._format_time(start_ms/1000)} - {self._format_time(end_ms/1000)}]"
                        segment_text = f"{timestamp} {processed_text}"
                        full_transcript.append(segment_text)
                        print(segment_text + "\n")  # Display each segment
                        
                        logger.info(f"✅ Segment {segment_num} completed in {elapsed:.2f}s")
                        yield {
                            "segment_text": segment_text,
                            "segment_num": segment_num,
                            "total_segments": total_segments,
                            "success": True
                        }
                    else:
                        logger.warning(f"⚠️ Segment {segment_num} returned empty result")
                        yield {
                            "segment_text": "",
                            "segment_num": segment_num,
                            "total_segments": total_segments,
                            "success": False
                        }
                        
                finally:
                    # Clean up temporary file
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"Transcription error: {str(e)}",
                "text": ""
            }
        """
        Transcribe audio file using SenseVoice with natural pause detection
        
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
            from pydub import AudioSegment
            import tempfile
            
            logger.info(f"🎤 Transcribing: {Path(audio_file_path).name}")
            logger.info(f"📊 Language: {language}")
            logger.info(f"📁 File size: {os.path.getsize(audio_file_path) / (1024*1024):.2f} MB")
            
            # Load audio
            audio = AudioSegment.from_file(audio_file_path)
            
            # Find speech segments
            segments = self.find_speech_segments(audio_file_path)
            
            full_transcript = []
            total_segments = len(segments)
            
            for idx, (start_ms, end_ms) in enumerate(segments):
                segment_num = idx + 1
                logger.info(f"🔄 Processing segment {segment_num}/{total_segments} "
                          f"[{start_ms/1000:.1f}s - {end_ms/1000:.1f}s]")
                
                # Extract segment
                segment = audio[start_ms:end_ms]
                
                # Save segment to temporary file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                    segment.export(tmp_file.name, format='wav')
                    tmp_path = tmp_file.name
                
                try:
                    # Transcribe segment
                    start_time = time.time()
                    
                    res = self.model.generate(
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
                        
                        # Add timestamp and text
                        timestamp = f"[{self._format_time(start_ms/1000)} - {self._format_time(end_ms/1000)}]"
                        segment_text = f"{timestamp} {processed_text}"
                        full_transcript.append(segment_text)
                        
                        logger.info(f"✅ Segment {segment_num} completed in {elapsed:.2f}s")
                    else:
                        logger.warning(f"⚠️ Segment {segment_num} returned empty result")
                        
                finally:
                    # Clean up temporary file
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
            
            # Join all segments
            final_transcript = "\n\n".join(full_transcript)
            
            logger.info(f"✅ Transcription completed successfully")
            logger.info(f"📝 Total text length: {len(final_transcript)} characters")
            
            return {
                "success": True,
                "text": final_transcript,
                "raw_text": final_transcript,
                "language": language,
                "file_path": audio_file_path,
                "num_segments": len(segments)
            }
            
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
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
                "Fast Inference"
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
