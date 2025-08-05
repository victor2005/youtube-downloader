#!/usr/bin/env python3
"""Test script to check SenseVoice dependencies"""

import sys

print("Python version:", sys.version)
print("-" * 50)

# Test imports
dependencies = [
    "funasr",
    "torch",
    "torchaudio",
    "librosa",
    "soundfile",
    "numpy",
    "scipy"
]

for dep in dependencies:
    try:
        __import__(dep)
        print(f"✅ {dep} - OK")
    except ImportError as e:
        print(f"❌ {dep} - FAILED: {e}")

print("-" * 50)

# Test SenseVoice initialization
try:
    from funasr import AutoModel
    print("✅ funasr.AutoModel - OK")
except Exception as e:
    print(f"❌ funasr.AutoModel - FAILED: {e}")

try:
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
    print("✅ funasr postprocess utils - OK")
except Exception as e:
    print(f"❌ funasr postprocess utils - FAILED: {e}")

print("-" * 50)
print("Test complete")
