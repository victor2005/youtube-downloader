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
    print('Downloading Whisper medium model...'); \
    from whisper import load_model; \
    model = load_model('medium', download_root='/app/models/whisper'); \
    print('Whisper medium model downloaded successfully')"

# Download SenseVoice model
RUN python -c "import os; \
    print('Downloading SenseVoice model...'); \
    from funasr import AutoModel; \
    model = AutoModel(model='iic/SenseVoiceSmall', cache_dir='/app/models/sensevoice'); \
    print('SenseVoice model downloaded successfully')"

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p downloads

# Expose port
EXPOSE 8080

# Disable model preloading at runtime since they're already in the image
ENV PRELOAD_MODELS=false

# Run the application
CMD ["python", "app.py"]
