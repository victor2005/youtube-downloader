// Hybrid Audio Transcription supporting both Whisper (client-side) and SenseVoice (server-side)
// This allows comparing both models for accuracy and performance

class TranscriptionManager {
    constructor() {
        this.worker = null;
        this.isLoading = false;
        this.currentModel = null;
        this.supportedFormats = ['.mp3', '.wav', '.m4a', '.ogg', '.webm', '.flac'];
        this.sensevoiceAvailable = false;
        this.fullTranscript = '';
        this.processedChunks = 0;
        this.totalChunks = 0;
        
        // Initialize UI elements
        this.initializeElements();
        this.bindEvents();
        this.loadAvailableAudioFiles();
        this.initializeWorker();
        this.checkSenseVoiceAvailability();
    }

    initializeElements() {
        this.elements = {
            section: document.getElementById('transcriptionSection'),
            audioFileSelect: document.getElementById('audioFileSelect'),
            languageSelect: document.getElementById('languageSelect'),
            transcribeBtn: document.getElementById('transcribeBtn'),
            progress: document.getElementById('transcriptionProgress'),
            progressFill: document.getElementById('transcriptionProgressFill'),
            status: document.getElementById('transcriptionProgressText'),
            result: document.getElementById('transcriptionResult'),
            transcriptText: document.getElementById('transcriptionText'),
            mainUrlInput: document.getElementById('url') // Use the main URL input
        };
        
        console.log('Elements initialized:', {
            transcribeBtn: this.elements.transcribeBtn,
            section: this.elements.section,
            mainUrlInput: this.elements.mainUrlInput
        });
    }

    bindEvents() {
        // Transcribe button click
        if (this.elements.transcribeBtn) {
            console.log('Binding click event to transcribe button');
            this.elements.transcribeBtn.addEventListener('click', (e) => {
                e.preventDefault(); // Prevent any form submission
                e.stopPropagation(); // Stop event bubbling
                console.log('Transcribe button clicked');
                this.startTranscription();
            });
        } else {
            console.error('Transcribe button not found!');
        }

        // Language selection change - reset pipeline when language changes
        if (this.elements.languageSelect) {
            this.elements.languageSelect.addEventListener('change', () => {
                this.pipeline = null; // Reset pipeline when language changes
                this.currentModel = null;
            });
        }

        // Audio file selection change
        if (this.elements.audioFileSelect) {
            this.elements.audioFileSelect.addEventListener('change', () => {
                this.updateTranscribeButtonState();
            });
        }

        // Main YouTube URL input change
        if (this.elements.mainUrlInput) {
            this.elements.mainUrlInput.addEventListener('input', () => {
                this.updateTranscribeButtonState();
            });
        }
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
        const hasUrl = this.elements.mainUrlInput?.value?.trim() !== '';
        const hasAudioFile = this.elements.audioFileSelect.value !== '';
        
        this.elements.transcribeBtn.disabled = this.isLoading || (!hasUrl && !hasAudioFile);
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
                const { chunkIndex, totalChunks, startTime, endTime } = message;
                
                this.updateStatus(`🔄 Processing [${this.formatTime(startTime)}-${this.formatTime(endTime)}] (${chunkIndex + 1}/${totalChunks})`, 
                    80 + ((chunkIndex + 1) / totalChunks) * 18);
                
                // Update UI to show current chunk being processed
                const currentChunkInfo = `\n🔄 Processing [${this.formatTime(startTime)}-${this.formatTime(endTime)}]...`;
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
        const { chunkIndex, text, processingTime, totalChunks, startTime, endTime } = message;
        
        // Validate timing data with fallbacks
        const timeStart = (startTime != null && !isNaN(startTime)) ? startTime : (chunkIndex * 30);
        const timeEnd = (endTime != null && !isNaN(endTime)) ? endTime : ((chunkIndex + 1) * 30);
        
        // Check for repetitive text patterns and filter them out
        const cleanedText = this.filterRepetitiveText(text);
        
        if (cleanedText && cleanedText.trim()) {
            const chunkLabel = `[${this.formatTime(timeStart)}-${this.formatTime(timeEnd)}]`;
            const speedInfo = `(${Math.round((processingTime || 0) / 1000)}s)`;
            const chunkTranscript = `${chunkLabel} ${speedInfo}\n${cleanedText.trim()}\n\n`;
            
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
            const { pipeline, env } = await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@latest');
            
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
            
            // Add debugging
            console.log('Loading audio file:', filename);
            
            const response = await fetch(`/download-file/${encodeURIComponent(filename)}`);
            if (!response.ok) {
                throw new Error(`Failed to load audio file: ${response.statusText}`);
            }

            const contentLength = response.headers.get('content-length');
            console.log('Audio file size:', contentLength ? (parseInt(contentLength) / 1024 / 1024).toFixed(2) + ' MB' : 'unknown');
            
            // Check file size before processing - increased limit to 150MB
            if (contentLength && parseInt(contentLength) > 150 * 1024 * 1024) { // 150MB limit
                throw new Error('Audio file too large (over 150MB). Please try downloading a shorter audio clip or use a lower quality format.');
            }
            
            // Show warning for large files
            if (contentLength && parseInt(contentLength) > 75 * 1024 * 1024) { // 75MB warning
                console.warn('Large audio file detected - transcription may take longer');
                this.updateStatus('Large file detected - this may take a while...', 62);
            }

            const arrayBuffer = await response.arrayBuffer();
            console.log('Audio buffer loaded, size:', (arrayBuffer.byteLength / 1024 / 1024).toFixed(2) + ' MB');
            
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
            }, 60000); // 60 second timeout
            
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
        const sampleRate = 16000;
        const { chunkDuration, overlapDuration } = this.getOptimalChunkSize(audioData.length, sampleRate);
        
        console.log(`Using adaptive chunking: ${chunkDuration}s chunks with ${overlapDuration}s overlap for ${Math.round(durationSeconds)}s audio`);
        
        // Use VAD-aware boundaries for better chunk splits
        const boundaries = this.calculateChunkBoundaries(audioData, sampleRate, chunkDuration);
        const totalChunks = boundaries.length;
        
        this.totalChunks = totalChunks;
        this.elements.transcriptText.textContent = `🎙️ Starting enhanced transcription with ${totalChunks} optimized chunks...\n\n`;
        
        const options = {
            return_timestamps: false,
            // Add these Whisper-specific optimizations for better quality
            condition_on_previous_text: true, // Better context continuity
            compression_ratio_threshold: 2.4,
            logprob_threshold: -1.0,
            no_speech_threshold: 0.6
        };
        
        if (language && language !== 'auto') {
            options.language = language;
            // Note: Cannot use forced_decoder_ids with language parameter
            // The language parameter should be sufficient for language consistency
        }
        
        for (let i = 0; i < totalChunks; i++) {
            const boundary = boundaries[i];
            
            // Use exact natural pause boundaries - no artificial overlap
            const startSample = boundary.start;
            const endSample = boundary.end;
            
            const chunk = audioData.slice(startSample, endSample);
            const chunkDuration = (endSample - startSample) / sampleRate;
            
            // Display times match the actual chunk boundaries exactly
            const startTime = startSample / sampleRate;
            const endTime = endSample / sampleRate;
            
            console.log(`Sending Chunk ${i + 1}/${totalChunks}: from sample ${startSample} to ${endSample} (${chunkDuration.toFixed(1)}s)`);
            console.log(`Natural pause chunk: ${startTime.toFixed(1)}s to ${endTime.toFixed(1)}s`);
            
            // Send chunk to worker for processing
            this.worker.postMessage({
                type: 'transcribeChunk',
                data: {
                    audioData: chunk,
                    options,
                    chunkIndex: i,
                    totalChunks,
                    chunkDuration: chunkDuration,
                    overlapDuration: 0, // No overlap with natural pause detection
                    hasOverlap: false, // Pure natural boundaries
                    startTime: startTime,
                    endTime: endTime
                }
            });
        }
        
        // Wait for all chunks to complete
        return new Promise((resolve, reject) => {
            const checkCompletion = () => {
                if (this.processedChunks >= totalChunks) {
                    const processedTranscript = this.postProcessTranscript(this.fullTranscript.trim());
                    resolve(processedTranscript);
                } else {
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
        // Handle invalid or null values
        if (seconds == null || isNaN(seconds) || seconds < 0) {
            return '0:00';
        }
        
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    // Use reasonable chunk sizes for good transcription quality
    getOptimalChunkSize(audioLength, sampleRate) {
        const totalDuration = audioLength / sampleRate;
        
        // Use moderate chunk sizes with reasonable overlap
        if (totalDuration < 60) {
            return { chunkDuration: 30, overlapDuration: 5 }; // 30s chunks with 5s overlap
        } else if (totalDuration < 300) {
            return { chunkDuration: 30, overlapDuration: 5 };
        } else {
            return { chunkDuration: 30, overlapDuration: 5 };
        }
    }

    // Smart chunking with natural pause detection
    calculateChunkBoundaries(audioData, sampleRate, baseChunkSize) {
        const boundaries = [];
        const baseSamples = baseChunkSize * sampleRate;
        const totalSamples = audioData.length;
        const minChunkSamples = 10 * sampleRate; // Minimum 10 seconds
        const maxChunkSamples = 45 * sampleRate; // Maximum 45 seconds
        
        console.log('Calculating natural pause boundaries...');
        
        let start = 0;
        while (start < totalSamples) {
            let idealEnd = Math.min(start + baseSamples, totalSamples);
            let actualEnd = idealEnd;
            
            // If this isn't the last chunk, look for natural pause
            if (idealEnd < totalSamples) {
                const searchStart = Math.max(start + minChunkSamples, idealEnd - 10 * sampleRate);
                const searchEnd = Math.min(idealEnd + 10 * sampleRate, totalSamples);
                
                const pauseLocation = this.findNaturalPause(audioData, searchStart, searchEnd, sampleRate);
                if (pauseLocation > 0) {
                    actualEnd = pauseLocation;
                    console.log(`Found natural pause at ${(pauseLocation / sampleRate).toFixed(1)}s`);
                }
            }
            
            boundaries.push({ start, end: actualEnd });
            
            // Move to next chunk
            start = actualEnd;
            if (start >= totalSamples) break;
        }
        
        console.log(`Created ${boundaries.length} chunks with natural boundaries`);
        return boundaries;
    }
    
    // Find natural pauses in audio using simple energy-based detection
    findNaturalPause(audioData, searchStart, searchEnd, sampleRate) {
        const windowSize = Math.floor(0.1 * sampleRate); // 100ms window
        const silenceThreshold = 0.01; // Adjust based on audio characteristics
        const minSilenceDuration = 0.3 * sampleRate; // Minimum 300ms silence
        
        let silenceStart = -1;
        let bestPauseLocation = -1;
        let longestSilence = 0;
        
        for (let i = searchStart; i < searchEnd - windowSize; i += windowSize) {
            // Calculate RMS energy for this window
            let energy = 0;
            for (let j = i; j < Math.min(i + windowSize, searchEnd); j++) {
                energy += audioData[j] * audioData[j];
            }
            energy = Math.sqrt(energy / windowSize);
            
            if (energy < silenceThreshold) {
                // Start of silence
                if (silenceStart === -1) {
                    silenceStart = i;
                }
            } else {
                // End of silence
                if (silenceStart !== -1) {
                    const silenceDuration = i - silenceStart;
                    if (silenceDuration >= minSilenceDuration && silenceDuration > longestSilence) {
                        longestSilence = silenceDuration;
                        bestPauseLocation = silenceStart + Math.floor(silenceDuration / 2);
                    }
                    silenceStart = -1;
                }
            }
        }
        
        // Check if we ended in silence
        if (silenceStart !== -1) {
            const silenceDuration = searchEnd - silenceStart;
            if (silenceDuration >= minSilenceDuration && silenceDuration > longestSilence) {
                bestPauseLocation = silenceStart + Math.floor(silenceDuration / 2);
            }
        }
        
        return bestPauseLocation;
    }

    // Post-processing for overlap deduplication with improved Chinese text handling
    postProcessTranscript(transcript) {
        const lines = transcript.split('\n\n');
        const processed = [];
        let continuousText = ''; // Track continuous narrative across chunks
        
        for (let i = 0; i < lines.length; i++) {
            if (!lines[i].trim()) continue;
            
            const match = lines[i].match(/^\[(\d+:\d+)-(\d+:\d+)\]/);
            if (!match) {
                processed.push(lines[i]);
                continue;
            }
            
            const text = lines[i].replace(/^\[[^\]]+\]\s*\([^)]+\)\s*/, '').trim();
            
            // Check for overlap with previous chunk
            if (i > 0 && processed.length > 0) {
                const prevText = processed[processed.length - 1].replace(/^\[[^\]]+\]\s*\([^)]+\)\s*/, '').trim();
                const overlap = this.findTextOverlap(prevText, text);
                
                if (overlap.length > 5) { // Lower threshold for Chinese text (5 characters instead of 10)
                    // For Chinese text, be more careful about character-based overlap
                    const overlapIndex = text.indexOf(overlap);
                    if (overlapIndex === 0) { // Overlap is at the beginning
                        const deduplicatedText = text.substring(overlap.length).trim();
                        if (deduplicatedText) {
                            // Replace the text in the line but keep timing and metadata
                            const processedLine = lines[i].replace(text, deduplicatedText);
                            processed.push(processedLine);
                            continuousText += ' ' + deduplicatedText;
                        }
                        continue;
                    }
                }
            }
            
            processed.push(lines[i]);
            continuousText += ' ' + text;
        }
        
        // Final cleanup: remove any remaining duplicate phrases
        return this.cleanupFinalTranscript(processed.join('\n\n'));
    }

    // Find overlapping text between two strings
    findTextOverlap(text1, text2) {
        const words1 = text1.split(' ');
        const words2 = text2.split(' ');
        
        let maxOverlap = '';
        
        // Look for overlapping sequences at the end of text1 and start of text2
        for (let i = 1; i <= Math.min(words1.length, words2.length, 20); i++) { // Limit to 20 words
            const end1 = words1.slice(-i).join(' ');
            const start2 = words2.slice(0, i).join(' ');
            
            if (end1.toLowerCase() === start2.toLowerCase() && end1.length > maxOverlap.length) {
                maxOverlap = start2;
            }
        }
        
        return maxOverlap;
    }

    // Filter out repetitive text patterns that Whisper sometimes generates
    filterRepetitiveText(text) {
        if (!text || typeof text !== 'string') return '';
        
        // Remove common repetitive patterns
        let cleaned = text.trim();
        
        // Pattern 1: "and the soul has a soul" type repetitions
        cleaned = cleaned.replace(/(and the \w+ has a \w+,?\s*){3,}/gi, '');
        
        // Pattern 2: Same phrase repeated multiple times
        const words = cleaned.split(/\s+/);
        const cleanedWords = [];
        let lastPhrase = '';
        let phraseCount = 0;
        
        for (let i = 0; i < words.length; i++) {
            const currentPhrase = words.slice(i, Math.min(i + 4, words.length)).join(' ').toLowerCase();
            
            if (currentPhrase === lastPhrase) {
                phraseCount++;
                if (phraseCount > 2) { // Skip if repeated more than 2 times
                    continue;
                }
            } else {
                phraseCount = 0;
                lastPhrase = currentPhrase;
            }
            
            cleanedWords.push(words[i]);
        }
        
        cleaned = cleanedWords.join(' ');
        
        // Pattern 3: Remove single words repeated many times
        cleaned = cleaned.replace(/(\b\w+\b)(?:\s+\1){4,}/gi, '$1');
        
        // Pattern 4: Clean up excessive punctuation
        cleaned = cleaned.replace(/[,，]{2,}/g, '，').replace(/[.。]{2,}/g, '。');
        
        return cleaned.trim();
    }

    // Final cleanup to remove remaining duplicates and improve readability
    cleanupFinalTranscript(transcript) {
        // Remove any duplicate sentences or phrases that might have slipped through
        const lines = transcript.split('\n');
        const cleanedLines = [];
        
        for (let line of lines) {
            // Skip empty lines but preserve structure
            if (line.trim() === '') {
                cleanedLines.push(line);
                continue;
            }
            
            // Clean up excessive spacing and punctuation
            line = line.replace(/\s+/g, ' ').trim();
            
            // Remove obvious duplicates (case-insensitive)
            const isDuplicate = cleanedLines.some(existingLine => {
                if (existingLine.trim() === '') return false;
                const existing = existingLine.toLowerCase().replace(/^\[[^\]]+\]\s*\([^)]+\)\s*/, '');
                const current = line.toLowerCase().replace(/^\[[^\]]+\]\s*\([^)]+\)\s*/, '');
                return existing === current && existing.length > 10;
            });
            
            if (!isDuplicate) {
                cleanedLines.push(line);
            }
        }
        
        return cleanedLines.join('\n');
    }

    async checkSenseVoiceAvailability() {
        try {
            console.log('Checking SenseVoice availability...');
            const response = await fetch('/sensevoice-status');
            const status = await response.json();
            
            this.sensevoiceAvailable = status.available;
            console.log('SenseVoice available:', this.sensevoiceAvailable);
            
            // Update model dropdown with SenseVoice option
            this.updateModelDropdown(status);
            
        } catch (error) {
            console.error('Failed to check SenseVoice availability:', error);
            this.sensevoiceAvailable = false;
        }
    }
    
    updateModelDropdown(sensevoiceStatus) {
        // No longer needed since we auto-select models
        console.log('Model auto-selection enabled, SenseVoice status:', sensevoiceStatus);
    }
    
    async transcribeWithSenseVoice(filename, language) {
        try {
            // Get selected SenseVoice model
            const sensevoiceModelSelect = document.getElementById('sensevoiceModelSelect');
            const modelName = sensevoiceModelSelect ? sensevoiceModelSelect.value : 'SenseVoiceSmall';
            
            this.updateStatus('🚀 Starting SenseVoice transcription...', 10);
            this.elements.transcriptText.textContent = '🎙️ Initializing SenseVoice transcription...\n\n';
            this.elements.result.style.display = 'block';
            
            // Initialize for streaming
            this.fullTranscript = '';
            this.processedChunks = 0;
            this.totalChunks = 0;
            
            const requestData = {
                filename: filename,
                language: language,
                model: modelName,
                streaming: true  // Enable streaming
            };
            
            console.log('Sending streaming transcription request to SenseVoice:', requestData);
            
            // Use EventSource for Server-Sent Events
            const eventSource = new EventSource(
                `/transcribe?${new URLSearchParams(requestData).toString()}`
            );
            
            return new Promise((resolve, reject) => {
                let finalTranscript = '';
                
                eventSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        
                        if (data.success && data.segment_text) {
                            // Handle streaming chunk
                            const { segment_text, segment_num, total_segments, processing_time } = data;
                            
                            // Update progress
                            const progress = 10 + (segment_num / total_segments) * 80;
                            this.updateStatus(
                                `🔄 Processing segment ${segment_num}/${total_segments}...`,
                                progress
                            );
                            
                            // Add to transcript
                            this.fullTranscript += segment_text + '\n\n';
                            finalTranscript = this.fullTranscript;
                            
                            // Update display in real-time
                            this.elements.transcriptText.textContent = this.fullTranscript + 
                                (segment_num < total_segments ? '\n⏳ Processing next segment...' : '');
                            
                            // Auto-scroll to bottom
                            this.elements.transcriptText.scrollTop = this.elements.transcriptText.scrollHeight;
                            
                            // If this is the last segment
                            if (segment_num === total_segments) {
                                eventSource.close();
                                this.updateStatus('✅ SenseVoice transcription complete!', 100);
                                
                                // Return just the transcript without model info
                                resolve(finalTranscript);
                            }
                        } else if (data.error) {
                            // Handle error
                            eventSource.close();
                            reject(new Error(data.error));
                        }
                    } catch (e) {
                        console.error('Error parsing SSE data:', e);
                    }
                };
                
                eventSource.onerror = (error) => {
                    eventSource.close();
                    
                    // If we have some transcript, it might just be the connection closing normally
                    if (finalTranscript) {
                        this.updateStatus('✅ SenseVoice transcription complete!', 100);
                        resolve(finalTranscript);
                    } else {
                        reject(new Error('Streaming connection failed'));
                    }
                };
            });
            
        } catch (error) {
            console.error('SenseVoice transcription error:', error);
            this.updateStatus(`❌ SenseVoice error: ${error.message}`, 0);
            throw error;
        }
    }

    async startTranscription() {
        if (this.isLoading) return;

        const selectedLanguage = this.elements.languageSelect.value;
        let selectedFile = this.elements.audioFileSelect.value;

        this.isLoading = true;
        this.elements.transcribeBtn.disabled = true;
        this.elements.transcribeBtn.textContent = '🔄 Transcribing...';
        this.elements.progress.style.display = 'block';
        this.elements.result.style.display = 'none';

        try {
            let transcript;

            const url = this.elements.mainUrlInput.value.trim();
            if (url) {
                console.log('Transcribing directly from URL:', url);
                transcript = await this.transcribeFromUrl(url, selectedLanguage);
            } else if (selectedFile) {
                // Auto-select model based on language
                const sensevoiceLanguages = ['zh', 'zh-CN', 'zh-TW', 'yue', 'ja', 'ko'];
const useSenseVoice = sensevoiceLanguages.includes(selectedLanguage) && this.sensevoiceAvailable;
                
                if (useSenseVoice) {
                    console.log('Using SenseVoice for transcription (language:', selectedLanguage, ')');
                    transcript = await this.transcribeWithSenseVoice(selectedFile, selectedLanguage);
                } else {
                    console.log('Using Whisper for transcription');
                    // Load the model (returns false if worker failed and we need fallback)
                    const modelLoaded = await this.loadModel('whisper-base');
                    
                    // If worker failed, modelLoaded will be false, and we'll use main thread fallback
                    if (modelLoaded === false) {
                        // Retry loading in main thread
                        await this.loadModel('whisper-base');
                    }

                    // Load the audio file
                    const audioBuffer = await this.loadAudioFile(selectedFile);

                    // Transcribe the audio
                    transcript = await this.transcribeAudio(audioBuffer, selectedLanguage);
                }
            } else {
                throw new Error('Please provide a YouTube URL or select an audio file.');
            }

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

    async transcribeFromUrl(url, language) {
        console.log('Starting transcription from URL with parameters:', { url, language });

        try {
            // Always use streaming for URL transcription (server will decide which model to use)
            console.log('Using streaming transcription for URL (language:', language, ')');
            return await this.transcribeFromUrlStreaming(url, language);
        } catch (error) {
            console.error('Failed to transcribe from URL:', error);
            throw error;
        }
    }

    async transcribeFromUrlWithWhisper(url, language) {
        console.log('Starting Whisper transcription from URL:', { url, language });
        
        try {
            // Step 1: Download audio from URL
            this.updateStatus('🔄 Downloading audio from URL...', 5);
            
            const downloadResponse = await fetch('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    url: url, 
                    format: 'mp3'  // Download as MP3 for transcription
                })
            });
            
            if (!downloadResponse.ok) {
                throw new Error('Failed to start download');
            }
            
            const downloadData = await downloadResponse.json();
            const downloadId = downloadData.download_id;
            
            // Step 2: Monitor download progress
            this.updateStatus('⏳ Downloading audio file...', 10);
            const filename = await this.waitForDownload(downloadId);
            
            if (!filename) {
                throw new Error('Download failed or timed out');
            }
            
            console.log('Audio downloaded successfully:', filename);
            
            // Step 3: Load Whisper model
            this.updateStatus('🤖 Loading Whisper model...', 30);
            const modelLoaded = await this.loadModel('whisper-base');
            
            if (modelLoaded === false) {
                // Retry loading in main thread
                await this.loadModel('whisper-base');
            }
            
            // Step 4: Load and transcribe the audio file
            this.updateStatus('📂 Loading audio file...', 50);
            const audioBuffer = await this.loadAudioFile(filename);
            
            // Step 5: Transcribe
            this.updateStatus('🎤 Starting transcription...', 70);
            const transcript = await this.transcribeAudio(audioBuffer, language);
            
            // Return just the transcript
            return transcript;
            
        } catch (error) {
            console.error('Whisper URL transcription error:', error);
            throw error;
        }
    }

    async waitForDownload(downloadId, maxWaitTime = 180000) { // 3 minutes max
        const startTime = Date.now();
        let lastPercent = 0;
        
        while (Date.now() - startTime < maxWaitTime) {
            try {
                const response = await fetch(`/progress/${downloadId}`);
                const progress = await response.json();
                
                if (progress.status === 'finished') {
                    // Get the downloaded file
                    const filesResponse = await fetch('/downloads?t=' + Date.now());
                    const files = await filesResponse.json();
                    
                    // Find the most recent audio file
                    const audioFiles = files.filter(file => 
                        this.supportedFormats.some(format => 
                            file.name.toLowerCase().endsWith(format)
                        )
                    ).sort((a, b) => b.modified - a.modified);
                    
                    if (audioFiles.length > 0) {
                        // Refresh the audio file dropdown
                        await this.loadAvailableAudioFiles();
                        return audioFiles[0].name;
                    }
                    
                    throw new Error('Downloaded file not found');
                    
                } else if (progress.status === 'error') {
                    throw new Error(progress.error || 'Download failed');
                    
                } else if (progress.status === 'downloading') {
                    // Update progress
                    const percent = parseInt(progress.percent) || 0;
                    if (percent > lastPercent) {
                        lastPercent = percent;
                        const downloadProgress = 10 + (percent * 0.15); // 10-25% of total progress
                        this.updateStatus(`⏬ Downloading: ${progress.percent} at ${progress.speed || 'N/A'}`, downloadProgress);
                    }
                }
                
                // Wait before checking again
                await new Promise(resolve => setTimeout(resolve, 1000));
                
            } catch (error) {
                console.error('Error checking download progress:', error);
                // Continue waiting
            }
        }
        
        throw new Error('Download timed out');
    }

    async transcribeFromUrlStreaming(url, language) {
        console.log('Starting streaming transcription from URL:', { url, language });
        
        // Check if we're on Railway (which doesn't support SSE well)
        const isRailway = window.location.hostname.includes('ytdownl.xyz') || 
                          window.location.hostname.includes('railway.app');
        
        if (isRailway) {
            console.log('Railway detected, using polling instead of SSE');
            return this.transcribeFromUrlPolling(url, language);
        }
        
        // Use SSE for local development
        return this.transcribeFromUrlSSE(url, language);
    }
    
    async transcribeFromUrlSSE(url, language) {
        console.log('Using SSE transcription for URL:', { url, language });
        
        // Build URL with query parameters for GET request
        const params = new URLSearchParams({
            url: url,
            language: language,
            streaming: 'true'
        });
        
        const eventSource = new EventSource(`/transcribe-url?${params}`);
        
        return new Promise((resolve, reject) => {
            let transcriptChunks = [];
            let finalTranscript = '';
            let modelInfo = '';
            
                eventSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        console.log('Received streaming data:', data);
                        
                        if (data.success) {
                            if (data.final) {
                                // Final result received
                                eventSource.close();
                                finalTranscript = data.transcript || transcriptChunks.join(' ');
                                this.updateStatus('✅ Transcription complete!', 100);
                                
                                // Update final display
                                this.elements.transcriptText.textContent = finalTranscript;
                                this.elements.result.style.display = 'block';
                                
                                resolve(finalTranscript);
                            } else {
                                // Chunk received
                                if (data.text) {
                                    transcriptChunks.push(data.text);
                                    // Update display with all chunks so far
                                    this.fullTranscript = transcriptChunks.join(' ');
                                    this.elements.transcriptText.textContent = this.fullTranscript + '\n\n⏳ Processing...';
                                    
                                    // Show result section if not visible
                                    if (this.elements.result.style.display === 'none') {
                                        this.elements.result.style.display = 'block';
                                    }
                                    
                                    // Auto-scroll to bottom
                                    this.elements.transcriptText.scrollTop = this.elements.transcriptText.scrollHeight;
                                    
                                    // Update progress
                                    const progress = Math.min(50 + (data.chunk * 5), 95);
                                    this.updateStatus(`🎤 Transcribing chunk ${data.chunk}...`, progress);
                                }
                            }
                        } else if (data.error) {
                            // Handle error
                            eventSource.close();
                            
                            // Check if we need to download first for client-side transcription
                            if (data.error.includes('download the audio file first')) {
                                reject(new Error('For this language, please download the audio file first, then use the "Downloaded File" option to transcribe with Whisper.'));
                            } else {
                                reject(new Error(data.error));
                            }
                        }
                    } catch (e) {
                        console.error('Error parsing SSE data:', e);
                    }
                };
            
            eventSource.onerror = (error) => {
                eventSource.close();
                
                // If we have some transcript, it might just be the connection closing normally
                if (transcriptChunks.length > 0) {
                    this.updateStatus('✅ Transcription complete!', 100);
                    finalTranscript = transcriptChunks.join(' ');
                    resolve(finalTranscript);
                } else {
                    reject(new Error('Streaming connection failed'));
                }
            };
            
            // Initial status
            this.updateStatus('🔄 Connecting to transcription service...', 10);
        });
    }
    
    async transcribeFromUrlPolling(url, language) {
        console.log('Using polling transcription for URL:', { url, language });
        
        // Start transcription with polling API
        const response = await fetch('/transcribe-url-poll', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: url,
                language: language
            })
        });
        
        if (!response.ok) {
            throw new Error(`Failed to start transcription: ${response.statusText}`);
        }
        
        const { session_id } = await response.json();
        console.log('Started polling transcription with session:', session_id);
        
        // Poll for progress
        return new Promise((resolve, reject) => {
            let lastChunkCount = 0;
            let transcriptChunks = [];
            
            const pollProgress = async () => {
                try {
                    const progressResponse = await fetch(`/transcribe-progress/${session_id}`);
                    const progress = await progressResponse.json();
                    
                    console.log('Polling progress:', progress);
                    console.log('Current chunks count:', progress.chunks ? progress.chunks.length : 0);
                    console.log('Last chunk count:', lastChunkCount);
                    console.log('Progress status:', progress.status);
                    console.log('Progress complete:', progress.complete);
                    
                    if (progress.status === 'not_found') {
                        reject(new Error('Transcription session not found'));
                        return;
                    }
                    
                    if (progress.error) {
                        reject(new Error(progress.error));
                        return;
                    }
                    
                    // Update UI with chunks
                    if (progress.chunks && progress.chunks.length > lastChunkCount) {
                        const newChunks = progress.chunks.slice(lastChunkCount);
                        transcriptChunks.push(...newChunks);
                        
                        // Update display
                        const partialTranscript = transcriptChunks.join(' ');
                        this.displayPartialTranscript(partialTranscript);
                        
                        // Update progress
                        const progressPercent = Math.min(50 + (progress.chunks.length * 5), 95);
                        this.updateStatus(`🎤 Processing chunk ${progress.chunks.length}...`, progressPercent);
                        
                        lastChunkCount = progress.chunks.length;
                    }
                    
                    if (progress.complete) {
                        if (progress.final_transcript) {
                            this.updateStatus('✅ Transcription complete!', 100);
                            resolve(progress.final_transcript);
                        } else {
                            const finalTranscript = transcriptChunks.join(' ');
                            this.updateStatus('✅ Transcription complete!', 100);
                            resolve(finalTranscript);
                        }
                    } else {
                        // Continue polling
                        setTimeout(pollProgress, 2000); // Poll every 2 seconds
                    }
                } catch (error) {
                    console.error('Polling error:', error);
                    reject(error);
                }
            };
            
            // Initial status
            this.updateStatus('🔄 Starting transcription...', 10);
            
            // Start polling
            setTimeout(pollProgress, 1000); // Start after 1 second
        });
    }

    displayPartialTranscript(text) {
        // Display partial transcript while streaming
        if (this.elements.transcriptText) {
            this.elements.transcriptText.textContent = text;
            if (this.elements.result.style.display === 'none') {
                this.elements.result.style.display = 'block';
            }
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
        // Use a more efficient approach with requestIdleCallback for better performance
        if (audioBuffer.numberOfChannels === 1) {
            return audioBuffer.getChannelData(0);
        }
        
        const length = audioBuffer.length;
        const monoData = new Float32Array(length);
        const numberOfChannels = audioBuffer.numberOfChannels;
        
        // Use much larger chunks and process with requestIdleCallback
        const chunkSize = Math.min(length, 1024 * 1024); // 1M samples or full length
        const totalChunks = Math.ceil(length / chunkSize);
        
        return new Promise((resolve, reject) => {
            let chunkIndex = 0;
            
            const processChunk = (deadline) => {
                try {
                    // Process multiple chunks within the time slice
                    while (chunkIndex < totalChunks && (!deadline || deadline.timeRemaining() > 0)) {
                        const start = chunkIndex * chunkSize;
                        const end = Math.min(start + chunkSize, length);
                        
                        // Optimized processing - get channel data once
                        const channelData = [];
                        for (let ch = 0; ch < numberOfChannels; ch++) {
                            channelData.push(audioBuffer.getChannelData(ch));
                        }
                        
                        // Process samples
                        for (let i = start; i < end; i++) {
                            let sum = 0;
                            for (let ch = 0; ch < numberOfChannels; ch++) {
                                sum += channelData[ch][i];
                            }
                            monoData[i] = sum / numberOfChannels;
                        }
                        
                        chunkIndex++;
                        
                        // Update progress less frequently
                        if (chunkIndex % Math.max(1, Math.floor(totalChunks / 10)) === 0) {
                            const progress = 72 + (chunkIndex / totalChunks) * 1;
                            this.updateStatus(`Converting to mono... ${Math.round((chunkIndex / totalChunks) * 100)}%`, progress);
                        }
                    }
                    
                    if (chunkIndex >= totalChunks) {
                        resolve(monoData);
                    } else {
                        // Schedule next chunk
                        if (window.requestIdleCallback) {
                            window.requestIdleCallback(processChunk, { timeout: 50 });
                        } else {
                            setTimeout(() => processChunk({ timeRemaining: () => 10 }), 0);
                        }
                    }
                } catch (error) {
                    reject(error);
                }
            };
            
            // Start processing
            if (window.requestIdleCallback) {
                window.requestIdleCallback(processChunk, { timeout: 50 });
            } else {
                setTimeout(() => processChunk({ timeRemaining: () => 10 }), 0);
            }
        });
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
        const ratio = sourceSampleRate / targetSampleRate;
        const sourceLength = sourceData.length;
        const targetLength = Math.round(sourceLength / ratio);
        const resampledData = new Float32Array(targetLength);
        
        // Use requestIdleCallback for non-blocking resampling
        return new Promise((resolve, reject) => {
            const chunkSize = Math.min(targetLength, 256 * 1024); // 256K samples per chunk
            const totalChunks = Math.ceil(targetLength / chunkSize);
            let chunkIndex = 0;
            
            const processChunk = (deadline) => {
                try {
                    // Process multiple chunks within the time slice
                    while (chunkIndex < totalChunks && (!deadline || deadline.timeRemaining() > 1)) {
                        const targetStart = chunkIndex * chunkSize;
                        const targetEnd = Math.min(targetStart + chunkSize, targetLength);
                        
                        // Optimized resampling loop
                        for (let i = targetStart; i < targetEnd; i++) {
                            const sourceIndex = i * ratio;
                            const sourceIndexFloor = Math.floor(sourceIndex);
                            const sourceIndexCeil = Math.min(sourceIndexFloor + 1, sourceLength - 1);
                            const fraction = sourceIndex - sourceIndexFloor;
                            resampledData[i] = sourceData[sourceIndexFloor] * (1 - fraction) + 
                                              sourceData[sourceIndexCeil] * fraction;
                        }
                        
                        chunkIndex++;
                        
                        // Update progress occasionally
                        if (chunkIndex % Math.max(1, Math.floor(totalChunks / 5)) === 0) {
                            const progress = 74 + (chunkIndex / totalChunks) * 1;
                            this.updateStatus(`Resampling... ${Math.round((chunkIndex / totalChunks) * 100)}%`, progress);
                        }
                    }
                    
                    if (chunkIndex >= totalChunks) {
                        resolve(resampledData);
                    } else {
                        // Schedule next chunk
                        if (window.requestIdleCallback) {
                            window.requestIdleCallback(processChunk, { timeout: 50 });
                        } else {
                            setTimeout(() => processChunk({ timeRemaining: () => 5 }), 0);
                        }
                    }
                } catch (error) {
                    reject(error);
                }
            };
            
            // Start processing
            if (window.requestIdleCallback) {
                window.requestIdleCallback(processChunk, { timeout: 50 });
            } else {
                setTimeout(() => processChunk({ timeRemaining: () => 5 }), 0);
            }
        });
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

    // Helper method to remove timestamps from transcript text
    removeTimestampsFromText(text) {
        if (!text) return '';
        
        // Remove timestamp patterns like [0:00-0:30] (3s) or [NaN:NaN-NaN:NaN]
        return text.replace(/\[\d+:\d{2}-\d+:\d{2}\]\s*\(\d+s\)|\[NaN:NaN-NaN:NaN\]\s*/g, '')
                  .replace(/\n\s*\n/g, '\n') // Remove extra blank lines
                  .trim();
    }

    copyTranscriptionToClipboard() {
        const transcript = this.elements.transcriptText.textContent;
        if (!transcript) {
            alert('No transcript to copy');
            return;
        }

        // Remove timestamps for cleaner text
        const cleanTranscript = this.removeTimestampsFromText(transcript);
        
        navigator.clipboard.writeText(cleanTranscript).then(() => {
            alert('Transcript copied to clipboard (timestamps removed)!');
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

        // Remove timestamps for cleaner text
        const cleanTranscript = this.removeTimestampsFromText(transcript);
        
        const filename = this.elements.audioFileSelect.value;
        const transcriptFilename = filename ? 
            filename.replace(/\.[^/.]+$/, '_transcript.txt') : 
            'transcript.txt';

        const blob = new Blob([cleanTranscript], { type: 'text/plain' });
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

// Make functions globally available
window.startTranscription = () => transcriptionManager?.startTranscription();
window.copyTranscription = () => transcriptionManager?.copyTranscriptionToClipboard();
window.downloadTranscription = () => transcriptionManager?.downloadTranscriptionAsText();
window.refreshLists = () => {
    transcriptionManager?.loadAvailableAudioFiles();
    if (window.loadDownloads) {
        window.loadDownloads();
    }
};

// No longer needed - URL is always visible and file input is in a collapsible details element
