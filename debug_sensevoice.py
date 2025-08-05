#!/usr/bin/env python3
"""
Debug script to test SenseVoice transcription directly
"""

import sys
import os
import time
import logging
from pathlib import Path

# Setup logging to see all details
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_sensevoice():
    """Test SenseVoice transcription with various settings"""
    
    # Find a test audio file
    test_files = []
    downloads_dir = Path("downloads")
    
    # Look for MP3 files in downloads
    for user_dir in downloads_dir.iterdir():
        if user_dir.is_dir():
            mp3_files = list(user_dir.glob("*.mp3"))
            if mp3_files:
                test_files.extend(mp3_files[:1])  # Take first file from each dir
    
    if not test_files:
        print("No test audio files found!")
        return
    
    # Test with first file
    test_file = str(test_files[0])
    print(f"\n🎵 Testing with file: {test_file}")
    print(f"📁 File size: {os.path.getsize(test_file) / (1024*1024):.2f} MB")
    
    try:
        # Method 1: Direct FunASR usage
        print("\n=== Method 1: Direct FunASR Test ===")
        from funasr import AutoModel
        
        print("Loading model...")
        model = AutoModel(
            model="iic/SenseVoiceSmall",
            trust_remote_code=True,
            device="cpu",
            disable_update=True,
            disable_log=False
        )
        
        print("Starting transcription...")
        start_time = time.time()
        
        # Try minimal settings first
        res = model.generate(
            input=test_file,
            language="zh",  # Force Chinese to avoid auto-detection issues
            batch_size_s=10  # Very small batch size
        )
        
        end_time = time.time()
        print(f"Transcription took: {end_time - start_time:.2f} seconds")
        
        if res and len(res) > 0:
            text = res[0].get("text", "")
            print(f"✅ Success! Text length: {len(text)} characters")
            print(f"First 200 chars: {text[:200]}")
        else:
            print("❌ No result returned")
            
    except Exception as e:
        print(f"❌ Error in Method 1: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        # Method 2: Test our wrapper
        print("\n=== Method 2: Testing our wrapper ===")
        from sensevoice_transcription import transcribe_with_sensevoice
        
        result = transcribe_with_sensevoice(test_file, language="zh")
        if result["success"]:
            print(f"✅ Success! Text length: {len(result['text'])} characters")
            print(f"First 200 chars: {result['text'][:200]}")
        else:
            print(f"❌ Failed: {result['error']}")
            
    except Exception as e:
        print(f"❌ Error in Method 2: {e}")
        import traceback
        traceback.print_exc()
    
    # Try to convert to WAV first
    try:
        print("\n=== Method 3: Convert to WAV first ===")
        from pydub import AudioSegment
        
        wav_file = test_file.replace('.mp3', '_test.wav')
        print(f"Converting to WAV: {wav_file}")
        
        audio = AudioSegment.from_mp3(test_file)
        # Downsample to 16kHz mono for better compatibility
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(wav_file, format="wav")
        
        print(f"WAV file created: {os.path.getsize(wav_file) / (1024*1024):.2f} MB")
        
        # Try with WAV file
        result = transcribe_with_sensevoice(wav_file, language="zh")
        if result["success"]:
            print(f"✅ Success with WAV! Text length: {len(result['text'])} characters")
            print(f"First 200 chars: {result['text'][:200]}")
        else:
            print(f"❌ Failed with WAV: {result['error']}")
            
        # Clean up
        if os.path.exists(wav_file):
            os.remove(wav_file)
            
    except Exception as e:
        print(f"❌ Error in Method 3: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_sensevoice()
