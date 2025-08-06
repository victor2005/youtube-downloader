FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with increased timeout
RUN pip install --no-cache-dir --timeout=300 -r requirements.txt

# Set environment variables for model caching before downloading
ENV WHISPER_CACHE_DIR=/app/models/whisper
ENV MODELSCOPE_CACHE=/app/models/sensevoice
ENV TRANSFORMERS_OFFLINE=0
ENV HF_HUB_DISABLE_PROGRESS_BARS=1

# Pre-download models during build with better error handling and progress
# Download Whisper medium model (larger but better quality)
RUN python -c "import os; os.environ['HF_HUB_DISABLE_PROGRESS_BARS']='0'; \
    print('Downloading Whisper small model...'); \
    from whisper import load_model; \
    model = load_model('small', download_root='/app/models/whisper'); \
    print('Whisper small model downloaded temporarily due to build timeout')"

# Download SenseVoice model
RUN python -c "import os; \
    print('Downloading SenseVoice model...'); \
    from funasr import AutoModel; \
    model = AutoModel(model='iic/SenseVoiceSmall', cache_dir='/app/models/sensevoice'); \
    print('SenseVoice model downloaded successfully')"

# Verify models are cached
RUN python -c "import os; \
    whisper_cache = '/app/models/whisper'; \
    sensevoice_cache = '/app/models/sensevoice'; \
    print('=== Verifying model cache ==='); \
    if os.path.exists(whisper_cache): \
        files = sum(len(files) for _, _, files in os.walk(whisper_cache)); \
        size = sum(os.path.getsize(os.path.join(dirpath, filename)) \
                  for dirpath, _, filenames in os.walk(whisper_cache) \
                  for filename in filenames) / (1024*1024); \
        print(f'✓ Whisper cache: {files} files, {size:.1f} MB'); \
    else: \
        print('✗ Whisper cache not found'); \
    if os.path.exists(sensevoice_cache): \
        files = sum(len(files) for _, _, files in os.walk(sensevoice_cache)); \
        size = sum(os.path.getsize(os.path.join(dirpath, filename)) \
                  for dirpath, _, filenames in os.walk(sensevoice_cache) \
                  for filename in filenames) / (1024*1024); \
        print(f'✓ SenseVoice cache: {files} files, {size:.1f} MB'); \
    else: \
        print('✗ SenseVoice cache not found')"

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p downloads

# Expose port
EXPOSE 8080

# Enable model preloading at runtime to use the cached models from build
ENV PRELOAD_MODELS=true

# Run startup check before the application
CMD python startup_check.py && python app.py
