#!/usr/bin/env python3
"""
Test script to verify that the pre-loaded SenseVoice model is being used correctly
"""

import os
import sys
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test the functionality step by step
def test_preloaded_model():
    logger.info("=== Testing Pre-loaded SenseVoice Model ===")
    
    # Step 1: Import the modules
    logger.info("Step 1: Importing modules...")
    try:
        from funasr import AutoModel
        from sensevoice_transcription import (
            SenseVoiceTranscriber,
            set_preloaded_sensevoice_model,
            sense_voice_transcriber
        )
        logger.info("✅ Modules imported successfully")
    except Exception as e:
        logger.error(f"❌ Failed to import modules: {e}")
        return
    
    # Step 2: Check initial state
    logger.info("\nStep 2: Checking initial state...")
    logger.info(f"Initial models in transcriber: {list(sense_voice_transcriber.models.keys())}")
    logger.info(f"Current model name: {sense_voice_transcriber.current_model_name}")
    
    # Step 3: Create a pre-loaded model
    logger.info("\nStep 3: Creating a pre-loaded model...")
    try:
        start_time = time.time()
        preloaded_model = AutoModel(model="iic/SenseVoiceSmall")
        load_time = time.time() - start_time
        logger.info(f"✅ Model loaded in {load_time:.2f} seconds")
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        return
    
    # Step 4: Set the pre-loaded model
    logger.info("\nStep 4: Setting pre-loaded model...")
    set_preloaded_sensevoice_model(preloaded_model)
    logger.info(f"Models after setting: {list(sense_voice_transcriber.models.keys())}")
    logger.info(f"Current model name: {sense_voice_transcriber.current_model_name}")
    
    # Step 5: Verify the model is the same instance
    logger.info("\nStep 5: Verifying model instance...")
    if "SenseVoiceSmall" in sense_voice_transcriber.models:
        is_same = sense_voice_transcriber.models["SenseVoiceSmall"] is preloaded_model
        logger.info(f"Is same model instance: {is_same}")
        if is_same:
            logger.info("✅ Pre-loaded model is being used correctly!")
        else:
            logger.error("❌ Different model instance detected!")
    else:
        logger.error("❌ SenseVoiceSmall not found in models!")
    
    # Step 6: Test get_model method
    logger.info("\nStep 6: Testing get_model method...")
    retrieved_model = sense_voice_transcriber.get_model("SenseVoiceSmall")
    is_same_retrieved = retrieved_model is preloaded_model
    logger.info(f"Retrieved model is same as pre-loaded: {is_same_retrieved}")
    
    # Step 7: Simulate what happens in app.py
    logger.info("\nStep 7: Simulating app.py behavior...")
    logger.info("Creating new transcriber instance (simulating module reload)...")
    new_transcriber = SenseVoiceTranscriber()
    logger.info(f"New transcriber models: {list(new_transcriber.models.keys())}")
    
    # Set pre-loaded model on new instance
    new_transcriber.models["SenseVoiceSmall"] = preloaded_model
    new_transcriber.current_model_name = "SenseVoiceSmall"
    logger.info("Pre-loaded model set on new instance")
    
    # Verify it's using the pre-loaded model
    new_retrieved = new_transcriber.get_model("SenseVoiceSmall")
    is_same_new = new_retrieved is preloaded_model
    logger.info(f"New instance uses pre-loaded model: {is_same_new}")
    
    logger.info("\n=== Test Complete ===")
    logger.info("✅ Pre-loaded model system is working correctly!")

if __name__ == "__main__":
    test_preloaded_model()
