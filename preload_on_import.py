"""
Module to ensure models are preloaded when the app is imported by WSGI servers
"""
import logging

# Import the preload function from app
try:
    from app import preload_models, PRELOADED_WHISPER, PRELOADED_SENSEVOICE
    
    # Check if models are already loaded
    if not PRELOADED_WHISPER and not PRELOADED_SENSEVOICE:
        logging.info("Preloading models on module import...")
        preload_models()
        logging.info("Models preloaded successfully on import")
    else:
        logging.info("Models already preloaded")
except Exception as e:
    logging.error(f"Failed to preload models on import: {e}")
