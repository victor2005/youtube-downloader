#!/usr/bin/env python3
"""Startup check script to verify models are loaded from cache"""

import os
import sys
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("=== STARTUP CHECK ===")
logging.info(f"Python version: {sys.version}")
logging.info(f"Working directory: {os.getcwd()}")

# Check environment variables
env_vars = ['WHISPER_CACHE_DIR', 'MODELSCOPE_CACHE', 'PRELOAD_MODELS']
for var in env_vars:
    value = os.environ.get(var, 'NOT SET')
    logging.info(f"{var}: {value}")

# Check if cache directories exist and have content
whisper_cache = os.environ.get('WHISPER_CACHE_DIR', '')
if whisper_cache and os.path.exists(whisper_cache):
    logging.info(f"✓ Whisper cache directory exists: {whisper_cache}")
    # Check for model files
    model_files = []
    for root, dirs, files in os.walk(whisper_cache):
        for file in files:
            if file.endswith(('.pt', '.pth', '.bin')):
                model_files.append(os.path.join(root, file))
    if model_files:
        logging.info(f"✓ Found {len(model_files)} model files in Whisper cache")
        for f in model_files[:3]:  # Show first 3 files
            size_mb = os.path.getsize(f) / (1024 * 1024)
            logging.info(f"  - {os.path.basename(f)}: {size_mb:.1f} MB")
    else:
        logging.warning("⚠ No model files found in Whisper cache")
else:
    logging.warning(f"⚠ Whisper cache directory does not exist: {whisper_cache}")

sensevoice_cache = os.environ.get('MODELSCOPE_CACHE', '')
if sensevoice_cache and os.path.exists(sensevoice_cache):
    logging.info(f"✓ SenseVoice cache directory exists: {sensevoice_cache}")
    # Check for model files
    model_files = []
    for root, dirs, files in os.walk(sensevoice_cache):
        for file in files:
            if file.endswith(('.pt', '.pth', '.bin', '.onnx')):
                model_files.append(os.path.join(root, file))
    if model_files:
        logging.info(f"✓ Found {len(model_files)} model files in SenseVoice cache")
        for f in model_files[:3]:  # Show first 3 files
            size_mb = os.path.getsize(f) / (1024 * 1024)
            logging.info(f"  - {os.path.basename(f)}: {size_mb:.1f} MB")
    else:
        logging.warning("⚠ No model files found in SenseVoice cache")
else:
    logging.warning(f"⚠ SenseVoice cache directory does not exist: {sensevoice_cache}")

logging.info("=== STARTUP CHECK COMPLETE ===")
