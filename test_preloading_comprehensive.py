#!/usr/bin/env python3
"""Comprehensive test to verify model preloading and reuse"""

import os
import sys
import logging
import time
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set environment variables
os.environ['PRELOAD_MODELS'] = 'true'
os.environ['WHISPER_CACHE_DIR'] = '/app/models/whisper'
os.environ['MODELSCOPE_CACHE'] = '/app/models/sensevoice'

logging.info("=== COMPREHENSIVE MODEL PRELOADING TEST ===")

# Test 1: Check if app.py preloading works
logging.info("\n[TEST 1] Testing app.py model preloading...")
try:
    # Import app which should trigger preloading
    import app
    
    # Wait a bit for background thread to complete
    logging.info("Waiting for background model loading...")
    time.sleep(5)
    
    # Check if models are loaded
    if app.PRELOADED_WHISPER:
        logging.info("✓ PRELOADED_WHISPER is set")
        logging.info(f"  Type: {type(app.PRELOADED_WHISPER)}")
        logging.info(f"  Model size: {app.PRELOADED_WHISPER.model_size}")
    else:
        logging.warning("⚠ PRELOADED_WHISPER is None")
    
    if app.PRELOADED_SENSEVOICE:
        logging.info("✓ PRELOADED_SENSEVOICE is set")
        logging.info(f"  Type: {type(app.PRELOADED_SENSEVOICE)}")
    else:
        logging.warning("⚠ PRELOADED_SENSEVOICE is None")
        
except Exception as e:
    logging.error(f"Failed to test app.py preloading: {e}")

# Test 2: Verify Whisper module uses preloaded model
logging.info("\n[TEST 2] Testing Whisper module preloaded model usage...")
try:
    from whisper_transcription import (
        transcribe_from_url_with_whisper,
        transcribe_from_url_streaming_whisper_generator,
        WhisperTranscriber
    )
    
    # Create a test audio array
    test_audio = np.random.randn(16000 * 5).astype(np.float32) * 0.1  # 5 seconds of noise
    
    # Test if passing preloaded model works
    if app.PRELOADED_WHISPER:
        logging.info("Testing transcription with preloaded model...")
        start_time = time.time()
        
        # Direct test with preloaded model
        result = app.PRELOADED_WHISPER.transcribe(test_audio, language='en')
        
        transcribe_time = time.time() - start_time
        logging.info(f"✓ Transcription with preloaded model took {transcribe_time:.2f}s")
        
        if transcribe_time < 10:
            logging.info("✓ Fast transcription indicates model was already loaded")
        else:
            logging.warning("⚠ Slow transcription might indicate model loading")
    else:
        logging.warning("⚠ No preloaded Whisper model to test")
        
except Exception as e:
    logging.error(f"Failed to test Whisper module: {e}")

# Test 3: Verify SenseVoice module uses preloaded model
logging.info("\n[TEST 3] Testing SenseVoice module preloaded model usage...")
try:
    from sensevoice_transcription import (
        transcribe_with_sensevoice_from_array,
        get_sensevoice_status
    )
    
    # Check SenseVoice status
    status = get_sensevoice_status()
    logging.info(f"SenseVoice status: {status}")
    
    if status.get('available'):
        # Test transcription
        test_audio = np.random.randn(16000 * 5).astype(np.float32) * 0.1  # 5 seconds of noise
        
        logging.info("Testing SenseVoice transcription...")
        start_time = time.time()
        
        result = transcribe_with_sensevoice_from_array(
            audio_array=test_audio,
            sample_rate=16000,
            language='zh',
            model_name='SenseVoiceSmall'
        )
        
        transcribe_time = time.time() - start_time
        logging.info(f"✓ SenseVoice transcription took {transcribe_time:.2f}s")
        
        if transcribe_time < 5:
            logging.info("✓ Fast transcription indicates model was already loaded")
        else:
            logging.warning("⚠ Slow transcription might indicate model loading")
    else:
        logging.warning("⚠ SenseVoice not available")
        
except Exception as e:
    logging.error(f"Failed to test SenseVoice module: {e}")

# Test 4: Verify models are shared across requests
logging.info("\n[TEST 4] Testing model sharing across multiple calls...")
try:
    if app.PRELOADED_WHISPER:
        # Make multiple transcription calls
        times = []
        for i in range(3):
            test_audio = np.random.randn(16000 * 2).astype(np.float32) * 0.1  # 2 seconds
            
            start_time = time.time()
            result = app.PRELOADED_WHISPER.transcribe(test_audio, language='en')
            elapsed = time.time() - start_time
            times.append(elapsed)
            
            logging.info(f"  Call {i+1}: {elapsed:.2f}s")
        
        # First call might be slower due to initialization, but subsequent calls should be fast
        if all(t < 5 for t in times[1:]):
            logging.info("✓ Subsequent calls are fast - model is being reused")
        else:
            logging.warning("⚠ Subsequent calls are slow - model might be reloading")
    else:
        logging.warning("⚠ No preloaded model to test")
        
except Exception as e:
    logging.error(f"Failed to test model sharing: {e}")

# Test 5: Memory check
logging.info("\n[TEST 5] Checking model memory usage...")
try:
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    
    logging.info(f"Current memory usage:")
    logging.info(f"  RSS: {memory_info.rss / 1024 / 1024:.1f} MB")
    logging.info(f"  VMS: {memory_info.vms / 1024 / 1024:.1f} MB")
    
    # Rough estimate: Whisper small ~100-200MB, SenseVoice ~200-400MB
    if memory_info.rss / 1024 / 1024 > 300:
        logging.info("✓ Memory usage suggests models are loaded")
    else:
        logging.warning("⚠ Memory usage seems low for loaded models")
        
except ImportError:
    logging.info("psutil not available, skipping memory check")
except Exception as e:
    logging.error(f"Failed to check memory: {e}")

logging.info("\n=== COMPREHENSIVE TEST COMPLETED ===")

# Summary
logging.info("\nSUMMARY:")
logging.info("- Models should be loaded once at startup in background thread")
logging.info("- All transcription calls should reuse the preloaded models")
logging.info("- This eliminates model loading delay for each transcription")
logging.info("- Models are shared across all users and requests")
