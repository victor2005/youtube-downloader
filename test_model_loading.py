#!/usr/bin/env python3
"""Test script to verify model loading behavior"""

import os
import logging
import time
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Allow override from command line
if len(sys.argv) > 1 and sys.argv[1] == 'local':
    # Local testing
    os.environ['WHISPER_CACHE_DIR'] = os.path.expanduser('~/.cache/whisper')
    os.environ['MODELSCOPE_CACHE'] = os.path.expanduser('~/.cache/modelscope')
else:
    # Docker-like testing
    os.environ['WHISPER_CACHE_DIR'] = '/app/models/whisper'
    os.environ['MODELSCOPE_CACHE'] = '/app/models/sensevoice'

os.environ['PRELOAD_MODELS'] = 'true'

logging.info("Starting model loading test...")
logging.info(f"WHISPER_CACHE_DIR: {os.environ.get('WHISPER_CACHE_DIR')}")
logging.info(f"MODELSCOPE_CACHE: {os.environ.get('MODELSCOPE_CACHE')}")
logging.info(f"PRELOAD_MODELS: {os.environ.get('PRELOAD_MODELS')}")

# Test Whisper loading
try:
    logging.info("Testing Whisper model loading...")
    start_time = time.time()
    
    import whisper
    
    # Check if model exists in cache
    cache_dir = os.environ.get('WHISPER_CACHE_DIR', '')
    if cache_dir and os.path.exists(cache_dir):
        logging.info(f"Whisper cache directory exists: {cache_dir}")
        logging.info(f"Contents: {os.listdir(cache_dir) if os.path.exists(cache_dir) else 'N/A'}")
    else:
        logging.warning(f"Whisper cache directory does not exist: {cache_dir}")
    
    # Try to load model
    model = whisper.load_model('small', download_root=cache_dir if cache_dir else None)
    
    load_time = time.time() - start_time
    logging.info(f"Whisper model loaded successfully in {load_time:.2f} seconds")
    
    # If it loaded very quickly (< 5 seconds), it's likely from cache
    if load_time < 5:
        logging.info("✓ Model likely loaded from cache (fast load time)")
    else:
        logging.warning("⚠ Model may have been downloaded (slow load time)")
        
except Exception as e:
    logging.error(f"Failed to load Whisper model: {e}")

# Test SenseVoice loading
try:
    logging.info("\nTesting SenseVoice model loading...")
    start_time = time.time()
    
    from funasr import AutoModel
    
    # Check if model exists in cache
    cache_dir = os.environ.get('MODELSCOPE_CACHE', '')
    if cache_dir and os.path.exists(cache_dir):
        logging.info(f"SenseVoice cache directory exists: {cache_dir}")
        logging.info(f"Contents: {os.listdir(cache_dir) if os.path.exists(cache_dir) else 'N/A'}")
    else:
        logging.warning(f"SenseVoice cache directory does not exist: {cache_dir}")
    
    # Try to load model
    model = AutoModel(model="iic/SenseVoiceSmall", cache_dir=cache_dir if cache_dir else None)
    
    load_time = time.time() - start_time
    logging.info(f"SenseVoice model loaded successfully in {load_time:.2f} seconds")
    
    # If it loaded very quickly (< 5 seconds), it's likely from cache
    if load_time < 5:
        logging.info("✓ Model likely loaded from cache (fast load time)")
    else:
        logging.warning("⚠ Model may have been downloaded (slow load time)")
        
except Exception as e:
    logging.error(f"Failed to load SenseVoice model: {e}")

logging.info("\nModel loading test completed.")
