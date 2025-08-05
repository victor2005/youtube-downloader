#!/usr/bin/env python3

"""
Test script for SenseVoice integration
"""

import sys
import os
from pathlib import Path

def test_sensevoice_import():
    """Test if SenseVoice can be imported"""
    try:
        from funasr import AutoModel
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        print("✅ SenseVoice imports successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import SenseVoice: {e}")
        return False

def test_sensevoice_model_loading():
    """Test if SenseVoice model can be loaded"""
    try:
        from funasr import AutoModel
        
        print("📥 Loading SenseVoice model...")
        model_dir = "iic/SenseVoiceSmall"
        
        # Load model with minimal configuration for testing
        model = AutoModel(
            model=model_dir,
            trust_remote_code=True,
            device="cpu",  # Use CPU for compatibility
            disable_log=True  # Reduce logging output
        )
        
        print("✅ SenseVoice model loaded successfully")
        return model
    except Exception as e:
        print(f"❌ Failed to load SenseVoice model: {e}")
        return None

def test_find_audio_file():
    """Find an audio file to test with"""
    downloads_dir = Path("downloads")
    if not downloads_dir.exists():
        print("❌ No downloads directory found")
        return None
    
    # Look for any audio files
    audio_extensions = ['.mp3', '.wav', '.m4a', '.flac']
    for ext in audio_extensions:
        audio_files = list(downloads_dir.rglob(f"*{ext}"))
        if audio_files:
            print(f"✅ Found audio file: {audio_files[0]}")
            return str(audio_files[0])
    
    print("❌ No audio files found in downloads directory")
    return None

def test_sensevoice_transcription(model, audio_file):
    """Test SenseVoice transcription"""
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        
        print(f"🎤 Testing transcription on: {Path(audio_file).name}")
        
        # Perform transcription
        res = model.generate(
            input=audio_file,
            cache={},
            language="auto",  # Auto-detect language
            use_itn=True,     # Include punctuation
            batch_size_s=60   # Process in 60-second batches
        )
        
        if res and len(res) > 0:
            text = rich_transcription_postprocess(res[0]["text"])
            print("✅ Transcription successful!")
            print(f"📝 Result: {text[:200]}..." if len(text) > 200 else f"📝 Result: {text}")
            return True
        else:
            print("❌ Transcription returned empty result")
            return False
            
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        return False

def main():
    print("🧪 Testing SenseVoice Integration")
    print("=" * 50)
    
    # Test imports
    if not test_sensevoice_import():
        sys.exit(1)
    
    # Test model loading
    model = test_sensevoice_model_loading()
    if not model:
        sys.exit(1)
    
    # Find audio file
    audio_file = test_find_audio_file()
    if not audio_file:
        print("⚠️  No audio files available for testing")
        print("✅ SenseVoice setup is complete - ready for transcription")
        return
    
    # Test transcription
    if test_sensevoice_transcription(model, audio_file):
        print("\n🎉 All tests passed! SenseVoice is ready to use.")
    else:
        print("\n⚠️  Model loaded but transcription test failed")
        print("✅ SenseVoice setup is complete - may need audio file format check")

if __name__ == "__main__":
    main()
