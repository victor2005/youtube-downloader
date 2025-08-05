#!/usr/bin/env python3
"""
Simple test for SenseVoice transcription
"""

import os
from pathlib import Path

def test_simple():
    """Simple test with the smallest MP3 file we can find"""
    
    # Find the smallest MP3 file
    downloads_dir = Path("downloads")
    smallest_file = None
    smallest_size = float('inf')
    
    for user_dir in downloads_dir.iterdir():
        if user_dir.is_dir():
            for mp3_file in user_dir.glob("*.mp3"):
                size = mp3_file.stat().st_size
                if size < smallest_size:
                    smallest_size = size
                    smallest_file = mp3_file
    
    if not smallest_file:
        print("No MP3 files found!")
        return
    
    print(f"Testing with smallest file: {smallest_file.name}")
    print(f"Size: {smallest_size / (1024*1024):.2f} MB")
    
    # Test import
    try:
        from sensevoice_transcription import transcribe_with_sensevoice
        print("✅ Import successful")
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return
    
    # Test transcription
    print("\nStarting transcription...")
    try:
        result = transcribe_with_sensevoice(str(smallest_file), language="zh")
        
        if result["success"]:
            print(f"✅ SUCCESS! Transcribed {len(result['text'])} characters")
            print(f"\nFirst 500 characters:")
            print(result['text'][:500])
        else:
            print(f"❌ Failed: {result['error']}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple()
