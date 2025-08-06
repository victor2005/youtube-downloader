#!/usr/bin/env python3

import subprocess
import numpy as np
import logging
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Test URL
url = "https://youtu.be/XLkpluZBrIA?si=-NGlRI9Ax2KNYor4"

# Extract audio URL using yt-dlp
import yt_dlp

logging.info(f"Extracting audio URL from: {url}")

ydl_opts = {'quiet': True, 'no_warnings': True}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    video_title = info.get('title', 'Unknown')
    duration = info.get('duration', 0)
    
    # Get best audio stream
    formats = info.get('formats', [])
    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
    
    if not audio_formats:
        audio_formats = [f for f in formats if f.get('acodec') != 'none']
    
    # Sort by audio quality
    audio_formats.sort(key=lambda f: f.get('abr', 0) or 0, reverse=True)
    
    best_audio = audio_formats[0] if audio_formats else None
    
    if not best_audio:
        logging.error("No audio stream found")
        exit(1)
    
    audio_url = best_audio['url']
    logging.info(f"Found audio stream: {best_audio.get('acodec')} at {best_audio.get('abr', 'unknown')} kbps")
    logging.info(f"Video duration: {duration} seconds")

# Use ffmpeg to stream
ffmpeg_cmd = [
    'ffmpeg',
    '-i', audio_url,
    '-f', 'wav',
    '-acodec', 'pcm_s16le',
    '-ar', '16000',
    '-ac', '1',
    '-'
]

logging.info("Starting ffmpeg process...")
process = subprocess.Popen(
    ffmpeg_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    bufsize=0
)

# Asynchronously capture and log stderr
def log_stderr():
    for line in iter(process.stderr.readline, b''):
        logging.info(f"ffmpeg stderr: {line.decode('utf-8').strip()}")

stderr_thread = threading.Thread(target=log_stderr)
stderr_thread.daemon = True
stderr_thread.start()

# Read the entire audio stream at once
logging.info("Reading entire ffmpeg audio output into buffer...")
audio_bytes = process.stdout.read()
total_bytes = len(audio_bytes)
logging.info(f"Finished reading audio stream. Total bytes: {total_bytes}")

# Wait for ffmpeg to finish
process.wait()
logging.info(f"FFmpeg process finished with return code: {process.returncode}")

# Convert to float array
audio_buffer = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
total_duration = len(audio_buffer) / 16000
logging.info(f"Total audio duration: {total_duration:.1f} seconds")

# Process in chunks (simulating transcription)
max_samples = 16000 * 15  # 15-second chunks
buffer_pos = 0
chunk_count = 0

while buffer_pos < len(audio_buffer):
    chunk_end = min(buffer_pos + max_samples, len(audio_buffer))
    process_chunk = audio_buffer[buffer_pos:chunk_end]
    
    if len(process_chunk) == 0:
        break
    
    chunk_count += 1
    chunk_duration = len(process_chunk) / 16000
    logging.info(f"Processing chunk {chunk_count}: {chunk_duration:.1f}s")
    
    buffer_pos = chunk_end

logging.info(f"Total chunks processed: {chunk_count}")
logging.info(f"Expected duration: {duration}s, Actual duration: {total_duration:.1f}s")
logging.info("Test completed successfully!")
