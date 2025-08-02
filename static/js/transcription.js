// Client-side Audio Transcription using Transformers.js with Web Workers
// This provides Whisper-powered transcription without blocking the UI

class TranscriptionManager {
    constructor() {
        this.worker = null;
        this.isLoading = false;
        this.currentModel = null;
        this.supportedFormats = ['.mp3', '.wav', '.m4a', '.ogg', '.webm'];
        this.fullTranscript = '';
        this.processedChunks = 0;
        this.totalChunks = 0;
        
        // Initialize UI elements
        this.initializeElements();
        this.bindEvents();
        this.loadAvailableAudioFiles();
        this.initializeWorker();
    }

    initializeElements() {
        this.elements = {
            section: document.getElementById('transcriptionSection'),
            audioFileSelect: document.getElementById('audioFileSelect'),
            modelSelect: document.getElementById('modelSelect'),
            languageSelect: document.getElementById('languageSelect'),
            transcribeBtn: document.getElementById('transcribeBtn'),
            progress: document.getElementById('transcriptionProgress'),
            progressFill: document.getElementById('transcriptionProgressFill'),
            status: document.getElementById('transcriptionProgressText'),
            result: document.getElementById('transcriptionResult'),
            transcriptText: document.getElementById('transcriptionText')
        };
    }

    bindEvents() {
        // Transcribe button click
        this.elements.transcribeBtn.addEventListener('click', () => {
            this.startTranscription();
        });

        // Model selection change
        this.elements.modelSelect.addEventListener('change', () => {
            this.pipeline = null; // Reset pipeline when model changes
            this.currentModel = null;
        });

        // Audio file selection change
        this.elements.audioFileSelect.addEventListener('change', () => {
            this.updateTranscribeButtonState();
        });
    }

    async loadAvailableAudioFiles() {
        try {
            console.log('Loading available audio files for transcription...');
            const response = await fetch('/downloads?t=' + Date.now());
            const files = await response.json();
            console.log('Files fetched from API:', files);
            
            // Filter audio files
            const audioFiles = files.filter(file => 
                this.supportedFormats.some(format => 
                    file.name.toLowerCase().endsWith(format)
                )
            );
            console.log('Filtered audio files:', audioFiles);
            console.log('Supported formats:', this.supportedFormats);

            // Populate dropdown
            this.elements.audioFileSelect.innerHTML = `<option value="">${window.i18n?.chooseAudioFile || 'Choose an audio file...'}</option>`;
            
            if (audioFiles.length === 0) {
                console.log('No audio files found, showing "No audio files available" message');
                const option = document.createElement('option');
                option.value = '';
                option.textContent = window.i18n?.noAudioFilesAvailable || 'No audio files available';
                option.disabled = true;
                this.elements.audioFileSelect.appendChild(option);
            } else {
                console.log(`Adding ${audioFiles.length} audio files to dropdown`);
                audioFiles.forEach(file => {
                    const option = document.createElement('option');
                    option.value = file.name;
                    option.textContent = `${file.name} (${this.formatFileSize(file.size)})`;
                    this.elements.audioFileSelect.appendChild(option);
                    console.log('Added audio file to dropdown:', file.name);
                });
            }

            this.updateTranscribeButtonState();
            console.log('Audio file loading completed');
        } catch (error) {
            console.error('Failed to load audio files:', error);
        }
    }

    updateTranscribeButtonState() {
        const hasAudioFile = this.elements.audioFileSelect.value !== '';
        this.elements.transcribeBtn.disabled = !hasAudioFile || this.isLoading;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    initializeWorker() {
        try {
            this.worker = new Worker('/static/js/transcription-worker.js');
            
            this.worker.onmessage = (e) => {
                this.handleWorkerMessage(e.data);
            };
            
            this.worker.onerror = (error) => {
                console.error('Worker error:', error);
            };
        } catch (error) {
            console.error('Failed to initialize worker:', error);
            // Fallback to main thread processing
            this.worker = null;
        }
    }

    handleWorkerMessage(message) {
        const { type } = message;
        
        switch (type) {
            case 'progress':
                this.updateStatus(message.message, message.percent);
                break;
                
            case 'modelLoaded':
                this.currentModel = message.model;
                this.updateStatus(`Model loaded (${message.device || 'WebGPU'})`, 50);
                break;
                
            case 'chunkStart':
                const { chunkIndex, totalChunks } = message;
                const timeStart = (chunkIndex * 8); // 8-second chunks
                const timeEnd = Math.min((chunkIndex + 1) * 8, this.audioDuration);
                
                this.updateStatus(`🔄 Processing [${this.formatTime(timeStart)}-${this.formatTime(timeEnd)}] (${chunkIndex + 1}/${totalChunks})`, 
                    80 + ((chunkIndex + 1) / totalChunks) * 18);
                
                // Update UI to show current chunk being processed
                const currentChunkInfo = `\n🔄 Processing [${this.formatTime(timeStart)}-${this.formatTime(timeEnd)}]...`;
                this.elements.transcriptText.textContent = this.fullTranscript + currentChunkInfo;
                break;
                
            case 'chunkComplete':
                this.handleChunkComplete(message);
                break;
                
            case 'chunkError':
                this.handleChunkError(message);
                break;
                
            case 'error':
                console.error('Worker error:', message.error);
                break;
        }
    }

    handleChunkComplete(message) {
        const { chunkIndex, text, processingTime, totalChunks } = message;
        const timeStart = chunkIndex * 8;
        const timeEnd = Math.min((chunkIndex + 1) * 8, this.audioDuration);
        
        if (text.trim()) {
            const chunkLabel = `[${this.formatTime(timeStart)}-${this.formatTime(timeEnd)}]`;
            const speedInfo = `(${Math.round(processingTime / 1000)}s)`;
            const chunkTranscript = `${chunkLabel} ${speedInfo}\n${text.trim()}\n\n`;
            
            this.fullTranscript += chunkTranscript;
        } else {
            const chunkLabel = `[${this.formatTime(timeStart)}-${this.formatTime(timeEnd)}]`;
            this.fullTranscript += `${chunkLabel} [Silent segment]\n\n`;
        }
        
        // Update display with new transcript
        this.elements.transcriptText.textContent = this.fullTranscript + 
            (chunkIndex < totalChunks - 1 ? '\n⏳ Next chunk loading...' : '\n✅ Transcription complete!');
        
        // Auto-scroll to bottom to show latest text
        this.elements.transcriptText.scrollTop = this.elements.transcriptText.scrollHeight;
        
        this.processedChunks++;
        
        if (this.processedChunks === totalChunks) {
            this.updateStatus('✅ Transcription complete!', 100);
        }
    }

    handleChunkError(message) {
        const { chunkIndex, error } = message;
        const timeStart = chunkIndex * 8;
        const timeEnd = Math.min((chunkIndex + 1) * 8, this.audioDuration);
        
        const chunkLabel = `[${this.formatTime(timeStart)}-${this.formatTime(timeEnd)}]`;
        this.fullTranscript += `${chunkLabel} ❌ [Error: ${error}]\n\n`;
        this.elements.transcriptText.textContent = this.fullTranscript;
        
        this.processedChunks++;
    }

    async loadModel(modelName) {
        if (this.worker) {
            // Use Web Worker for model loading
            this.updateStatus(window.i18n?.loadingAIModel || 'Loading AI model...', 10);
            
            try {
                this.worker.postMessage({
                    type: 'loadModel',
                    data: { modelName }
                });
                
                // Wait for model to load with timeout
                return new Promise((resolve, reject) => {
                    const originalHandler = this.worker.onmessage;
                    
                    const timeout = setTimeout(() => {
                        this.worker.onmessage = originalHandler;
                        console.warn('Worker model loading timed out, falling back to main thread');
                        this.worker = null; // Disable worker for future use
                        resolve(false); // Signal to use fallback
                    }, 60000); // 1 minute timeout
                    
                    this.worker.onmessage = (e) => {
                        if (e.data.type === 'modelLoaded') {
                            clearTimeout(timeout);
                            this.worker.onmessage = originalHandler;
                            resolve(true);
                        } else if (e.data.type === 'error') {
                            clearTimeout(timeout);
                            this.worker.onmessage = originalHandler;
                            console.warn('Worker model loading failed, falling back to main thread:', e.data.error);
                            this.worker = null; // Disable worker for future use
                            resolve(false); // Signal to use fallback
                        } else {
                            originalHandler(e);
                        }
                    };
                });
            } catch (error) {
                console.warn('Worker error, falling back to main thread:', error);
                this.worker = null;
                return false;
            }
        }
        
        // Fallback to main thread if no worker
        if (this.currentModel === modelName && this.pipeline) {
            return this.pipeline;
        }

        this.updateStatus('Loading AI model...', 10);
        
        try {
            // Import Transformers.js dynamically - use latest version for better performance
            const { pipeline, env } = await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2');
            
            // Configure for better performance
            env.allowRemoteModels = true;
            env.allowLocalModels = false;
            
            this.updateStatus('Initializing Whisper model...', 30);
            
            // Use optimized model configuration based on Hugging Face recommendations
            const modelId = 'Xenova/whisper-base'; // Use the optimized base model directly
            
            this.pipeline = await pipeline('automatic-speech-recognition', modelId, {
                // Optimized quantization settings for speed
                dtype: {
                    encoder_model: 'fp16', // Use fp16 for better performance
                    decoder_model_merged: 'q8', // Use q8 quantization for balance of speed/quality
                },
                device: 'webgpu', // Try WebGPU first
                // Add progress callback for model loading
                progress_callback: (progress) => {
                    if (progress.status === 'downloading') {
                        const percent = Math.round((progress.loaded / progress.total) * 100);
                        this.updateStatus(`Downloading model... ${percent}%`, 10 + percent * 0.4);
                    }
                },
            });

            this.currentModel = modelName;
            this.updateStatus('Model loaded successfully', 50);
            
            return this.pipeline;
        } catch (error) {
            console.error('Error loading model:', error);
            
            // Fallback to CPU with optimized settings
            try {
                const { pipeline, env } = await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2');
                
                this.updateStatus('Loading model (CPU fallback)...', 35);
                
                this.pipeline = await pipeline('automatic-speech-recognition', 'Xenova/whisper-base', {
                    dtype: {
                        encoder_model: 'fp32',
                        decoder_model_merged: 'q8', // Still use quantization on CPU
                    },
                    device: 'cpu',
                    progress_callback: (progress) => {
                        if (progress.status === 'downloading') {
                            const percent = Math.round((progress.loaded / progress.total) * 100);
                            this.updateStatus(`Downloading model (CPU)... ${percent}%`, 35 + percent * 0.15);
                        }
                    },
                });

                this.currentModel = modelName;
                this.updateStatus('Model loaded (CPU mode)', 50);
                
                return this.pipeline;
            } catch (fallbackError) {
                console.error('CPU fallback also failed:', fallbackError);
                throw new Error(`Failed to load model: ${fallbackError.message}`);
            }
        }
    }

    async loadAudioFile(filename) {
        try {
            this.updateStatus('Loading audio file...', 60);
            
            const response = await fetch(`/download-file/${encodeURIComponent(filename)}`);
            if (!response.ok) {
                throw new Error(`Failed to load audio file: ${response.statusText}`);
            }

            const arrayBuffer = await response.arrayBuffer();
            this.updateStatus('Processing audio...', 70);
            
            // Process audio in chunks to prevent blocking
            return this.processAudioInChunks(arrayBuffer);
        } catch (error) {
            console.error('Error loading audio file:', error);
            throw error;
        }
    }

    async processAudioInChunks(arrayBuffer) {
        return new Promise((resolve, reject) => {
            // Step 1: Decode audio
            this.updateStatus('Decoding audio file...', 71);
            
            // Use a more conservative AudioContext configuration
            const audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000, // Target sample rate to reduce processing
                latencyHint: 'playback' // Optimize for efficiency over low latency
            });
            
            // Set a timeout for the entire audio processing
            const processingTimeout = setTimeout(() => {
                audioContext.close();
                reject(new Error('Audio processing timed out - file may be too large or corrupted'));
            }, 30000); // 30 second timeout
            
            audioContext.decodeAudioData(arrayBuffer)
                .then(audioBuffer => {
                    
                    this.updateStatus('Converting to mono...', 72);
                    
                    // Step 2: Convert to mono with smaller chunks and progress updates
                    this.convertToMonoAsync(audioBuffer)
                        .then(monoData => {
                            this.updateStatus('Resampling to 16kHz...', 74);
                            
                            // Step 3: Resample if needed
                            const targetSampleRate = 16000;
                            if (audioBuffer.sampleRate !== targetSampleRate) {
                                this.resampleAudioAsync(monoData, audioBuffer.sampleRate, targetSampleRate)
                                    .then(finalAudioData => {
                                        clearTimeout(processingTimeout);
                                        audioContext.close();
                                        this.updateStatus('Audio processed successfully', 75);
                                        resolve(finalAudioData);
                                    })
                                    .catch(error => {
                                        clearTimeout(processingTimeout);
                                        audioContext.close();
                                        reject(error);
                                    });
                            } else {
                                clearTimeout(processingTimeout);
                                audioContext.close();
                                this.updateStatus('Audio processed successfully', 75);
                                resolve(monoData);
                            }
                        })
                        .catch(error => {
                            clearTimeout(processingTimeout);
                            audioContext.close();
                            reject(error);
                        });
                })
                .catch(error => {
                    clearTimeout(processingTimeout);
                    audioContext.close();
                    reject(new Error(`Failed to decode audio: ${error.message}`));
                });
        });
    }

    async transcribeAudio(audioData, language) {
        try {
            this.updateStatus('Preparing transcription...', 80);
            
            // Show initial streaming message
            this.elements.transcriptText.textContent = 'Initializing transcription...';
            this.elements.result.style.display = 'block';

            // Calculate audio duration for progress tracking
            const sampleRate = 16000; // We resampled to 16kHz
            const durationSeconds = audioData.length / sampleRate;
            this.audioDuration = durationSeconds; // Store for worker callbacks
            
            this.updateStatus(`Transcribing ${Math.round(durationSeconds)}s of audio...`, 82);
            
            // Reset transcription state
            this.fullTranscript = '';
            this.processedChunks = 0;
            
            if (this.worker) {
                // Use Web Worker for better responsiveness
                return this.streamingTranscribeWithWorker(audioData, language, durationSeconds);
            } else {
                // Fallback to main thread processing
                return this.streamingTranscribe(audioData, language, durationSeconds);
            }
        } catch (error) {
            console.error('Error during transcription:', error);
            this.elements.transcriptText.textContent = `Transcription failed: ${error.message}`;
            throw error;
        }
    }

    async streamingTranscribeWithWorker(audioData, language, durationSeconds) {
        // Use 8-second chunks for optimal worker performance
        const chunkDuration = 8;
        const sampleRate = 16000;
        const samplesPerChunk = chunkDuration * sampleRate;
        const totalChunks = Math.ceil(audioData.length / samplesPerChunk);
        
        this.totalChunks = totalChunks;
        this.elements.transcriptText.textContent = '🎙️ Starting transcription...\n\n';
        
        // Prepare transcription options
        const options = {
            return_timestamps: false,
        };
        
        // Add language constraint if not auto-detect
        if (language && language !== 'auto') {
            options.language = language;
        }
        
        // Process chunks in the worker
        const chunkPromises = [];
        
        for (let i = 0; i < totalChunks; i++) {
            const startSample = i * samplesPerChunk;
            const endSample = Math.min(startSample + samplesPerChunk, audioData.length);
            const chunk = audioData.slice(startSample, endSample);
            
            // Send chunk to worker for processing
            this.worker.postMessage({
                type: 'transcribeChunk',
                data: {
                    audioData: chunk,
                    options,
                    chunkIndex: i,
                    totalChunks
                }
            });
        }
        
        // Wait for all chunks to complete
        return new Promise((resolve, reject) => {
            const checkCompletion = () => {
                if (this.processedChunks >= totalChunks) {
                    resolve(this.fullTranscript.trim());
                } else {
                    // Check again in a bit
                    setTimeout(checkCompletion, 100);
                }
            };
            
            checkCompletion();
            
            // Set a reasonable timeout (30 seconds per chunk)
            setTimeout(() => {
                if (this.processedChunks < totalChunks) {
                    reject(new Error('Transcription timeout'));
                }
            }, totalChunks * 30000);
        });
    }

    async streamingTranscribe(audioData, language, durationSeconds) {
        // Use smaller chunks for faster streaming and better user experience
        const chunkDuration = 10; // Process 10-second chunks for faster streaming
        const sampleRate = 16000;
        const samplesPerChunk = chunkDuration * sampleRate;
        const totalChunks = Math.ceil(audioData.length / samplesPerChunk);
        
        let fullTranscript = '';
        let processedChunks = 0;
        
        this.elements.transcriptText.textContent = '🎙️ Starting transcription...\n\n';
        
        try {
            // Process audio in smaller chunks for faster streaming
            for (let i = 0; i < totalChunks; i++) {
                const startSample = i * samplesPerChunk;
                const endSample = Math.min(startSample + samplesPerChunk, audioData.length);
                const chunk = audioData.slice(startSample, endSample);
                
                // Update progress with more granular updates
                const chunkProgress = 82 + ((i + 1) / totalChunks) * 13;
                const timeProcessed = Math.min((i + 1) * chunkDuration, Math.round(durationSeconds));
                this.updateStatus(`🔄 Processing ${timeProcessed}s / ${Math.round(durationSeconds)}s (${i + 1}/${totalChunks})`, chunkProgress);
                
                // Show current chunk being processed
                const currentChunkInfo = `\n🔄 Processing [${this.formatTime(i * chunkDuration)}-${this.formatTime(Math.min((i + 1) * chunkDuration, durationSeconds))}]...`;
                this.elements.transcriptText.textContent = fullTranscript + currentChunkInfo;
                
                // Optimized transcription options for speed
                const options = {
                    // Use smaller internal chunks for faster processing
                    chunk_length_s: 10,
                    stride_length_s: 2,
                    // Optimize for speed
                    return_timestamps: false,
                };

                // Add language constraint if not auto-detect
                if (language && language !== 'auto') {
                    options.language = language;
                }

                try {
                    // Show transcription in progress
                    const startTime = Date.now();
                    
                    // Transcribe this chunk with timeout protection
                    const transcriptionPromise = this.pipeline(chunk, options);
                    const timeoutPromise = new Promise((_, reject) => 
                        setTimeout(() => reject(new Error('Chunk timeout')), 30000)
                    );
                    
                    const result = await Promise.race([transcriptionPromise, timeoutPromise]);
                    const processingTime = Date.now() - startTime;
                    
                    const chunkText = result.text || result || '';
                    
                    if (chunkText.trim()) {
                        // Add chunk text to full transcript with timing info
                        const chunkLabel = `[${this.formatTime(i * chunkDuration)}-${this.formatTime(Math.min((i + 1) * chunkDuration, durationSeconds))}]`;
                        const speedInfo = `(${Math.round(processingTime / 1000)}s)`;
                        const chunkTranscript = `${chunkLabel} ${speedInfo}\n${chunkText.trim()}\n\n`;
                        
                        fullTranscript += chunkTranscript;
                        
                        // Update display immediately with new text
                        this.elements.transcriptText.textContent = fullTranscript + 
                            (i < totalChunks - 1 ? '\n⏳ Next chunk loading...' : '\n✅ Transcription complete!');
                        
                        // Scroll to bottom to show latest text
                        this.elements.transcriptText.scrollTop = this.elements.transcriptText.scrollHeight;
                    } else {
                        // Handle empty chunks
                        const chunkLabel = `[${this.formatTime(i * chunkDuration)}-${this.formatTime(Math.min((i + 1) * chunkDuration, durationSeconds))}]`;
                        fullTranscript += `${chunkLabel} [Silent segment]\n\n`;
                        this.elements.transcriptText.textContent = fullTranscript;
                    }
                    
                    processedChunks++;
                } catch (chunkError) {
                    console.warn(`Error transcribing chunk ${i + 1}:`, chunkError);
                    const chunkLabel = `[${this.formatTime(i * chunkDuration)}-${this.formatTime(Math.min((i + 1) * chunkDuration, durationSeconds))}]`;
                    fullTranscript += `${chunkLabel} ❌ [Error: ${chunkError.message}]\n\n`;
                    this.elements.transcriptText.textContent = fullTranscript;
                }
                
                // Minimal delay to keep UI responsive
                await new Promise(resolve => setTimeout(resolve, 50));
            }
            
            this.updateStatus('✅ Transcription complete!', 100);
            return fullTranscript.trim();
            
        } catch (error) {
            console.error('Streaming transcription error:', error);
            throw error;
        }
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    async startTranscription() {
        if (this.isLoading) return;

        const selectedFile = this.elements.audioFileSelect.value;
        const selectedModel = this.elements.modelSelect.value;
        const selectedLanguage = this.elements.languageSelect.value;

        if (!selectedFile) {
            alert('Please select an audio file first.');
            return;
        }

        this.isLoading = true;
        this.elements.transcribeBtn.disabled = true;
        this.elements.transcribeBtn.textContent = '🔄 Transcribing...';
        this.elements.progress.style.display = 'block';
        this.elements.result.style.display = 'none';

        try {
            // Load the model (returns false if worker failed and we need fallback)
            const modelLoaded = await this.loadModel(selectedModel);
            
            // If worker failed, modelLoaded will be false, and we'll use main thread fallback
            if (modelLoaded === false) {
                // Retry loading in main thread
                await this.loadModel(selectedModel);
            }

            // Load the audio file
            const audioBuffer = await this.loadAudioFile(selectedFile);

            // Transcribe the audio
            const transcript = await this.transcribeAudio(audioBuffer, selectedLanguage);

            // Display results
            this.displayTranscript(transcript);

        } catch (error) {
            console.error('Transcription failed:', error);
            this.updateStatus(`Error: ${error.message}`, 0);
            alert(`Transcription failed: ${error.message}`);
        } finally {
            this.isLoading = false;
            this.elements.transcribeBtn.disabled = false;
            this.elements.transcribeBtn.textContent = '🎤 Start Transcription';
        }
    }

    displayTranscript(transcript) {
        this.elements.transcriptText.textContent = transcript;
        this.elements.result.style.display = 'block';
        this.elements.progress.style.display = 'none';
    }

    updateStatus(message, progress) {
        this.elements.status.textContent = message;
        if (progress !== undefined) {
            this.elements.progressFill.style.width = `${progress}%`;
        }
    }

    convertToMono(audioBuffer) {
        // Convert stereo to mono by averaging channels
        if (audioBuffer.numberOfChannels === 1) {
            return audioBuffer.getChannelData(0);
        }
        
        const length = audioBuffer.length;
        const monoData = new Float32Array(length);
        
        for (let i = 0; i < length; i++) {
            let sum = 0;
            for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
                sum += audioBuffer.getChannelData(channel)[i];
            }
            monoData[i] = sum / audioBuffer.numberOfChannels;
        }
        
        return monoData;
    }

    async convertToMonoAsync(audioBuffer) {
        // Async version that processes in chunks with progress updates
        if (audioBuffer.numberOfChannels === 1) {
            return audioBuffer.getChannelData(0);
        }
        
        const length = audioBuffer.length;
        const monoData = new Float32Array(length);
        const chunkSize = 88200; // Process 2 seconds at a time at 44.1kHz
        const totalChunks = Math.ceil(length / chunkSize);
        
        for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
            const start = chunkIndex * chunkSize;
            const end = Math.min(start + chunkSize, length);
            
            // Process this chunk
            for (let i = start; i < end; i++) {
                let sum = 0;
                for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
                    sum += audioBuffer.getChannelData(channel)[i];
                }
                monoData[i] = sum / audioBuffer.numberOfChannels;
            }
            
            // Update progress and yield control
            const progress = 72 + (chunkIndex / totalChunks) * 1;
            this.updateStatus(`Converting to mono... ${Math.round((chunkIndex / totalChunks) * 100)}%`, progress);
            
            // Yield control to prevent blocking
            if (chunkIndex < totalChunks - 1) {
                await new Promise(resolve => setTimeout(resolve, 1));
            }
        }
        
        return monoData;
    }

    convertToMonoChunked(audioBuffer) {
        // Non-blocking version that processes in smaller chunks
        if (audioBuffer.numberOfChannels === 1) {
            return audioBuffer.getChannelData(0);
        }
        
        const length = audioBuffer.length;
        const monoData = new Float32Array(length);
        const chunkSize = 44100; // Process 1 second at a time at 44.1kHz
        
        for (let start = 0; start < length; start += chunkSize) {
            const end = Math.min(start + chunkSize, length);
            
            for (let i = start; i < end; i++) {
                let sum = 0;
                for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
                    sum += audioBuffer.getChannelData(channel)[i];
                }
                monoData[i] = sum / audioBuffer.numberOfChannels;
            }
        }
        
        return monoData;
    }

    resampleAudio(audioBuffer, targetSampleRate) {
        // Simple linear interpolation resampling
        const sourceSampleRate = audioBuffer.sampleRate;
        const ratio = sourceSampleRate / targetSampleRate;
        
        // Get mono audio data
        const sourceData = audioBuffer.numberOfChannels > 1 ? 
            this.convertToMono(audioBuffer) : 
            audioBuffer.getChannelData(0);
        
        const sourceLength = sourceData.length;
        const targetLength = Math.round(sourceLength / ratio);
        const resampledData = new Float32Array(targetLength);
        
        for (let i = 0; i < targetLength; i++) {
            const sourceIndex = i * ratio;
            const sourceIndexFloor = Math.floor(sourceIndex);
            const sourceIndexCeil = Math.min(sourceIndexFloor + 1, sourceLength - 1);
            const fraction = sourceIndex - sourceIndexFloor;
            
            // Linear interpolation
            resampledData[i] = sourceData[sourceIndexFloor] * (1 - fraction) + 
                              sourceData[sourceIndexCeil] * fraction;
        }
        
        return resampledData;
    }

    async resampleAudioAsync(sourceData, sourceSampleRate, targetSampleRate) {
        // Async version of resampling that processes in chunks with progress updates
        const ratio = sourceSampleRate / targetSampleRate;
        const sourceLength = sourceData.length;
        const targetLength = Math.round(sourceLength / ratio);
        const resampledData = new Float32Array(targetLength);
        
        const chunkSize = Math.round(32000); // Process ~2 seconds at 16kHz at a time
        const totalChunks = Math.ceil(targetLength / chunkSize);
        
        for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
            const targetStart = chunkIndex * chunkSize;
            const targetEnd = Math.min(targetStart + chunkSize, targetLength);
            
            // Process this chunk
            for (let i = targetStart; i < targetEnd; i++) {
                const sourceIndex = i * ratio;
                const sourceIndexFloor = Math.floor(sourceIndex);
                const sourceIndexCeil = Math.min(sourceIndexFloor + 1, sourceLength - 1);
                const fraction = sourceIndex - sourceIndexFloor;
                
                // Linear interpolation
                resampledData[i] = sourceData[sourceIndexFloor] * (1 - fraction) + 
                                  sourceData[sourceIndexCeil] * fraction;
            }
            
            // Update progress and yield control
            const progress = 74 + (chunkIndex / totalChunks) * 1;
            this.updateStatus(`Resampling to 16kHz... ${Math.round((chunkIndex / totalChunks) * 100)}%`, progress);
            
            // Yield control to prevent blocking
            if (chunkIndex < totalChunks - 1) {
                await new Promise(resolve => setTimeout(resolve, 1));
            }
        }
        
        return resampledData;
    }

    resampleAudioChunked(sourceData, sourceSampleRate, targetSampleRate) {
        // Non-blocking resampling that processes in chunks
        const ratio = sourceSampleRate / targetSampleRate;
        const sourceLength = sourceData.length;
        const targetLength = Math.round(sourceLength / ratio);
        const resampledData = new Float32Array(targetLength);
        
        const chunkSize = Math.round(16000); // Process ~1 second at 16kHz at a time
        
        for (let targetStart = 0; targetStart < targetLength; targetStart += chunkSize) {
            const targetEnd = Math.min(targetStart + chunkSize, targetLength);
            
            for (let i = targetStart; i < targetEnd; i++) {
                const sourceIndex = i * ratio;
                const sourceIndexFloor = Math.floor(sourceIndex);
                const sourceIndexCeil = Math.min(sourceIndexFloor + 1, sourceLength - 1);
                const fraction = sourceIndex - sourceIndexFloor;
                
                // Linear interpolation
                resampledData[i] = sourceData[sourceIndexFloor] * (1 - fraction) + 
                                  sourceData[sourceIndexCeil] * fraction;
            }
        }
        
        return resampledData;
    }

    copyTranscriptionToClipboard() {
        const transcript = this.elements.transcriptText.textContent;
        if (!transcript) {
            alert('No transcript to copy');
            return;
        }

        navigator.clipboard.writeText(transcript).then(() => {
            alert('Transcript copied to clipboard!');
        }).catch(err => {
            console.error('Failed to copy transcript:', err);
            alert('Failed to copy transcript to clipboard');
        });
    }

    downloadTranscriptionAsText() {
        const transcript = this.elements.transcriptText.textContent;
        if (!transcript) {
            alert('No transcript to download');
            return;
        }

        const filename = this.elements.audioFileSelect.value;
        const transcriptFilename = filename ? 
            filename.replace(/\.[^/.]+$/, '_transcript.txt') : 
            'transcript.txt';

        const blob = new Blob([transcript], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = transcriptFilename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        window.URL.revokeObjectURL(url);
    }

    // Public method to show/hide transcription section
    show() {
        this.elements.section.style.display = 'block';
        this.loadAvailableAudioFiles(); // Refresh file list
    }

    hide() {
        this.elements.section.style.display = 'none';
    }
}

// Initialize transcription manager when DOM is loaded
let transcriptionManager;

// Wait for DOM to be fully loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeTranscription);
} else {
    // DOM is already loaded
    initializeTranscription();
}

function initializeTranscription() {
    // Only initialize if elements exist
    if (document.getElementById('transcriptionSection')) {
        console.log('Initializing TranscriptionManager...');
        transcriptionManager = new TranscriptionManager();
        window.transcriptionManager = transcriptionManager;
        console.log('TranscriptionManager initialized successfully');
    } else {
        console.log('Transcription section not found, retrying...');
        // Retry after a short delay if elements don't exist yet
        setTimeout(initializeTranscription, 100);
    }
}

// Export for use in other scripts
window.TranscriptionManager = TranscriptionManager;
