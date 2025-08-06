#!/usr/bin/env python3
"""
Test script to debug streaming/polling transcription delays
"""

import os
import sys
import time
import requests
import json
from pathlib import Path

# Check if models are cached
def check_model_cache():
    """Check if Whisper and SenseVoice models are properly cached"""
    print("=== Checking Model Cache ===")
    
    # Check Whisper cache
    whisper_cache = Path.home() / '.cache' / 'whisper'
    if whisper_cache.exists():
        print(f"✓ Whisper cache directory exists: {whisper_cache}")
        models = list(whisper_cache.glob("*.pt"))
        for model in models:
            size_mb = model.stat().st_size / (1024 * 1024)
            print(f"  - {model.name}: {size_mb:.1f} MB")
    else:
        print(f"✗ Whisper cache directory not found: {whisper_cache}")
    
    # Check SenseVoice cache
    sensevoice_cache = Path.home() / '.cache' / 'modelscope'
    if sensevoice_cache.exists():
        print(f"✓ SenseVoice cache directory exists: {sensevoice_cache}")
        # Find model files
        model_files = list(sensevoice_cache.rglob("*.pt")) + list(sensevoice_cache.rglob("*.bin"))
        for model in model_files:
            size_mb = model.stat().st_size / (1024 * 1024)
            relative_path = model.relative_to(sensevoice_cache)
            print(f"  - {relative_path}: {size_mb:.1f} MB")
    else:
        print(f"✗ SenseVoice cache directory not found: {sensevoice_cache}")

def test_polling_endpoint(base_url="http://127.0.0.1:8080"):
    """Test the polling transcription endpoint directly"""
    print("\n=== Testing Polling Transcription ===")
    
    # Test URL (short video for testing)
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" - 19 seconds
    
    # Start transcription
    print(f"Starting transcription for: {test_url}")
    response = requests.post(f"{base_url}/transcribe-url-poll", 
                           json={"url": test_url, "language": "auto"})
    
    if response.status_code != 200:
        print(f"✗ Failed to start transcription: {response.status_code}")
        print(response.text)
        return
    
    session_id = response.json().get("session_id")
    print(f"✓ Started transcription with session ID: {session_id}")
    
    # Poll for progress
    start_time = time.time()
    last_chunk_count = 0
    chunks_received = []
    
    while True:
        time.sleep(2)  # Poll every 2 seconds
        
        progress_response = requests.get(f"{base_url}/transcribe-progress/{session_id}")
        if progress_response.status_code != 200:
            print(f"✗ Failed to get progress: {progress_response.status_code}")
            break
            
        progress = progress_response.json()
        elapsed = time.time() - start_time
        
        # Check for new chunks
        if progress.get("chunks"):
            current_chunk_count = len(progress["chunks"])
            if current_chunk_count > last_chunk_count:
                new_chunks = progress["chunks"][last_chunk_count:]
                for chunk in new_chunks:
                    chunks_received.append(chunk)
                    print(f"[{elapsed:.1f}s] Chunk {len(chunks_received)}: {chunk[:50]}...")
                last_chunk_count = current_chunk_count
        
        # Check status
        status = progress.get("status", "unknown")
        print(f"[{elapsed:.1f}s] Status: {status}, Chunks: {len(chunks_received)}")
        
        if progress.get("complete"):
            print(f"\n✓ Transcription completed in {elapsed:.1f} seconds")
            if progress.get("final_transcript"):
                print(f"Final transcript length: {len(progress['final_transcript'])} chars")
            break
        
        if progress.get("error"):
            print(f"\n✗ Error: {progress['error']}")
            break
        
        if elapsed > 300:  # 5 minute timeout
            print(f"\n✗ Timeout after {elapsed:.1f} seconds")
            break

def test_streaming_endpoint(base_url="http://127.0.0.1:8080"):
    """Test the SSE streaming endpoint directly"""
    print("\n=== Testing SSE Streaming ===")
    
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    
    # Make SSE request
    print(f"Starting SSE streaming for: {test_url}")
    
    import sseclient  # You may need to: pip install sseclient-py
    
    response = requests.get(
        f"{base_url}/transcribe-url",
        params={"url": test_url, "language": "auto", "streaming": "true"},
        stream=True
    )
    
    if response.status_code != 200:
        print(f"✗ Failed to start streaming: {response.status_code}")
        return
    
    client = sseclient.SSEClient(response)
    start_time = time.time()
    chunk_count = 0
    
    print("Receiving SSE events...")
    for event in client.events():
        elapsed = time.time() - start_time
        try:
            data = json.loads(event.data)
            chunk_count += 1
            
            if data.get("text"):
                print(f"[{elapsed:.1f}s] Chunk {chunk_count}: {data['text'][:50]}...")
            
            if data.get("final"):
                print(f"\n✓ Streaming completed in {elapsed:.1f} seconds")
                break
                
        except Exception as e:
            print(f"[{elapsed:.1f}s] Error parsing event: {e}")

if __name__ == "__main__":
    # Check model cache first
    check_model_cache()
    
    # Test endpoints
    if len(sys.argv) > 1 and sys.argv[1] == "--test-endpoints":
        try:
            test_polling_endpoint()
        except Exception as e:
            print(f"Polling test failed: {e}")
        
        try:
            test_streaming_endpoint()
        except Exception as e:
            print(f"Streaming test failed: {e}")
