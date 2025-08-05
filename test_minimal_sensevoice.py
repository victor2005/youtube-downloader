#!/usr/bin/env python3
"""
Minimal test to isolate SenseVoice issue
"""

import logging
import time

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_direct_sensevoice():
    """Test SenseVoice directly with minimal settings"""
    
    print("=" * 60)
    print("SenseVoice Minimal Test")
    print("=" * 60)
    
    # Step 1: Test import
    print("\n1. Testing imports...")
    try:
        from funasr import AutoModel
        print("✅ FunASR imported successfully")
    except Exception as e:
        print(f"❌ Failed to import FunASR: {e}")
        return
    
    # Step 2: Test model loading
    print("\n2. Loading SenseVoice model...")
    try:
        start = time.time()
        model = AutoModel(
            model="iic/SenseVoiceSmall",
            trust_remote_code=True,
            device="cpu",
            disable_update=True
        )
        print(f"✅ Model loaded in {time.time() - start:.2f}s")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 3: Create a very simple test
    print("\n3. Testing with text input...")
    try:
        # First try with direct text
        result = model.generate(
            input="测试一下这个模型是否能够正常工作",
            language="zh"
        )
        if result:
            print(f"✅ Text test successful: {result}")
        else:
            print("❌ Text test returned empty result")
    except Exception as e:
        print(f"❌ Text test failed: {e}")
    
    # Step 4: Find smallest audio file
    print("\n4. Finding test audio file...")
    from pathlib import Path
    
    test_file = None
    min_size = float('inf')
    
    for f in Path("downloads").rglob("*.mp3"):
        size = f.stat().st_size
        if size < min_size:
            min_size = size
            test_file = f
    
    if not test_file:
        print("❌ No MP3 files found")
        return
    
    print(f"Found test file: {test_file.name}")
    print(f"Size: {min_size / (1024*1024):.2f} MB")
    
    # Step 5: Test with actual audio
    print("\n5. Testing transcription with minimal settings...")
    try:
        start = time.time()
        
        # Try with absolute minimal settings
        result = model.generate(
            input=str(test_file),
            language="zh"  # Force Chinese
        )
        
        elapsed = time.time() - start
        print(f"⏱️ Transcription took {elapsed:.2f}s")
        
        if result and len(result) > 0:
            text = result[0].get("text", "")
            print(f"✅ Success! Got {len(text)} characters")
            print(f"First 200 chars: {text[:200]}")
        else:
            print("❌ No result returned")
            
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_direct_sensevoice()
