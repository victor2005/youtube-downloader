import asyncio
import tempfile
from typing import AsyncGenerator, Optional
import yt_dlp
import numpy as np
from pydub import AudioSegment
import io
import logging

class StreamingTranscriber:
    """
    Efficient streaming transcription that processes audio chunks as they download
    """
    
    def __init__(self, model_type: str = "whisper"):
        self.model_type = model_type
        self.chunk_duration = 30  # Process 30-second chunks
        self.buffer_size = 1024 * 1024  # 1MB buffer
        
    async def transcribe_from_url(self, url: str, language: str = "auto") -> AsyncGenerator[dict, None]:
        """
        Stream audio from URL and transcribe in chunks without saving full file
        """
        # Create a temporary buffer for streaming
        with tempfile.SpooledTemporaryFile(max_size=10*1024*1024) as temp_buffer:
            
            # Configure yt-dlp for streaming
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                # Stream to buffer instead of file
                'outtmpl': '-',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',  # WAV for direct processing
                    'preferredquality': '16',  # 16kHz for speech models
                }],
            }
            
            # Start downloading/streaming
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get duration
                info = ydl.extract_info(url, download=False)
                duration = info.get('duration', 0)
                
                yield {
                    'type': 'start',
                    'duration': duration,
                    'title': info.get('title', 'Unknown')
                }
                
                # Stream download with progress callback
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        downloaded = d.get('downloaded_bytes', 0)
                        total = d.get('total_bytes', 0)
                        
                        # Check if we have enough data for a chunk
                        if downloaded > self.buffer_size:
                            # Process available audio
                            temp_buffer.seek(0)
                            audio_data = temp_buffer.read()
                            
                            # Reset buffer for next chunk
                            temp_buffer.seek(0)
                            temp_buffer.truncate()
                            
                            # Process this chunk asynchronously
                            asyncio.create_task(self._process_audio_chunk(audio_data, language))
                
                ydl.params['progress_hooks'] = [progress_hook]
                
                # Alternative: Use ffmpeg directly for true streaming
                await self._stream_with_ffmpeg(url, language)
    
    async def _stream_with_ffmpeg(self, url: str, language: str):
        """
        Use ffmpeg for true audio streaming without intermediate download
        """
        import subprocess
        
        # Get direct stream URL from yt-dlp
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Find best audio stream
            audio_url = None
            for fmt in info.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_url = fmt.get('url')
                    break
            
            if not audio_url:
                raise Exception("No audio stream found")
        
        # Stream with ffmpeg
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', audio_url,
            '-f', 'wav',
            '-acodec', 'pcm_s16le',
            '-ar', '16000',  # 16kHz for speech models
            '-ac', '1',      # Mono
            '-'              # Output to stdout
        ]
        
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        # Process audio in chunks as it streams
        chunk_size = 16000 * 30  # 30 seconds of audio at 16kHz
        audio_buffer = bytearray()
        
        while True:
            # Read chunk from ffmpeg output
            chunk = await process.stdout.read(chunk_size * 2)  # 2 bytes per sample
            
            if not chunk:
                # Process remaining audio
                if audio_buffer:
                    yield await self._transcribe_chunk(audio_buffer, language)
                break
            
            audio_buffer.extend(chunk)
            
            # Process when we have enough audio
            if len(audio_buffer) >= chunk_size * 2:
                # Extract chunk
                chunk_data = audio_buffer[:chunk_size * 2]
                audio_buffer = audio_buffer[chunk_size * 2:]
                
                # Transcribe this chunk
                result = await self._transcribe_chunk(chunk_data, language)
                yield result
    
    async def _transcribe_chunk(self, audio_data: bytes, language: str) -> dict:
        """
        Transcribe a single audio chunk
        """
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Here you would call your transcription model
        # For example, with Whisper:
        # transcript = whisper_model.transcribe(audio_array, language=language)
        
        # Simulated transcription result
        return {
            'type': 'transcript',
            'text': f"Transcribed chunk of {len(audio_array)/16000:.1f} seconds",
            'timestamp': len(audio_array) / 16000
        }


# More efficient approach: Download once, process in parallel chunks
class ParallelTranscriber:
    """
    Download audio once but process chunks in parallel for speed
    """
    
    def __init__(self, model_type: str = "whisper", num_workers: int = 4):
        self.model_type = model_type
        self.num_workers = num_workers
        self.chunk_duration = 30  # seconds
        
    async def transcribe_from_url(self, url: str, language: str = "auto") -> dict:
        """
        Download audio and transcribe chunks in parallel
        """
        # Download audio to memory-efficient format
        audio_data = await self._download_audio(url)
        
        # Split into chunks
        chunks = self._split_audio(audio_data, self.chunk_duration)
        
        # Process chunks in parallel
        tasks = []
        for i, chunk in enumerate(chunks):
            task = asyncio.create_task(
                self._transcribe_chunk_with_timing(chunk, i, language)
            )
            tasks.append(task)
        
        # Wait for all chunks
        results = await asyncio.gather(*tasks)
        
        # Combine results
        full_transcript = " ".join([r['text'] for r in sorted(results, key=lambda x: x['index'])])
        
        return {
            'transcript': full_transcript,
            'chunks': results,
            'processing_time': sum(r['time'] for r in results)
        }
    
    async def _download_audio(self, url: str) -> np.ndarray:
        """
        Download and convert audio to numpy array efficiently
        """
        # Use yt-dlp to get audio stream
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '16',
            }],
            'outtmpl': '-',  # Output to stdout
        }
        
        # Stream to memory
        audio_buffer = io.BytesIO()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            # Process audio_buffer
            
        return np.frombuffer(audio_buffer.getvalue(), dtype=np.int16)
    
    def _split_audio(self, audio: np.ndarray, chunk_duration: int) -> list:
        """
        Split audio into chunks with overlap for better continuity
        """
        sample_rate = 16000
        chunk_samples = chunk_duration * sample_rate
        overlap_samples = 2 * sample_rate  # 2 second overlap
        
        chunks = []
        start = 0
        
        while start < len(audio):
            end = min(start + chunk_samples, len(audio))
            chunk = audio[start:end]
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start += chunk_samples - overlap_samples
            
        return chunks
    
    async def _transcribe_chunk_with_timing(self, chunk: np.ndarray, index: int, language: str) -> dict:
        """
        Transcribe a chunk and measure time
        """
        import time
        start_time = time.time()
        
        # Actual transcription would happen here
        # transcript = model.transcribe(chunk, language=language)
        
        # Simulated result
        result = {
            'index': index,
            'text': f"Chunk {index} transcript",
            'time': time.time() - start_time
        }
        
        return result


# Usage example
async def main():
    # Method 1: True streaming (processes as it downloads)
    transcriber = StreamingTranscriber()
    async for result in transcriber.transcribe_from_url("https://youtube.com/watch?v=xxx", "en"):
        if result['type'] == 'transcript':
            print(f"Chunk: {result['text']}")
    
    # Method 2: Parallel processing (faster overall)
    parallel_transcriber = ParallelTranscriber(num_workers=4)
    result = await parallel_transcriber.transcribe_from_url("https://youtube.com/watch?v=xxx", "en")
    print(f"Full transcript: {result['transcript']}")
    print(f"Total processing time: {result['processing_time']:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
