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

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download models during build
# This ensures models are baked into the image
RUN python -c "from whisper import load_model; load_model('base', download_root='/app/models/whisper')"
RUN python -c "from funasr import AutoModel; AutoModel(model='iic/SenseVoiceSmall', cache_dir='/app/models/sensevoice')"

# Copy application code
COPY . .

# Set environment variables to use cached models
ENV WHISPER_CACHE_DIR=/app/models/whisper
ENV MODELSCOPE_CACHE=/app/models/sensevoice

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "app.py"]
