// Web Worker for Whisper Transcription
// This runs in a separate thread to keep the UI responsive

let pipeline = null;
let currentModel = null;
let transformersLoaded = false;

// Load Transformers.js in the worker using dynamic import
async function loadTransformers() {
    try {
        // Try to load the transformers library
        const transformers = await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@latest/dist/transformers.min.js');
        
        // Set up the environment
        transformers.env.allowRemoteModels = true;
        transformers.env.allowLocalModels = false;
        
        // Store the pipeline function globally
        self.pipeline = transformers.pipeline;
        transformersLoaded = true;
        
        self.postMessage({
            type: 'transformersLoaded'
        });
        
        return transformers;
    } catch (error) {
        console.error('Failed to load Transformers.js:', error);
        self.postMessage({
            type: 'error',
            error: 'Failed to load Transformers.js: ' + error.message
        });
        throw error;
    }
}

// Load transformers when the worker starts
loadTransformers().catch(error => {
    console.error('Worker initialization failed:', error);
});

// Message handler
self.onmessage = async function(e) {
    const { type, data } = e.data;
    
    try {
        switch (type) {
            case 'loadModel':
                await loadModel(data.modelName);
                break;
            case 'transcribeChunk':
                await transcribeChunk(
                    data.audioData, 
                    data.options, 
                    data.chunkIndex, 
                    data.totalChunks,
                    data.chunkDuration,
                    data.overlapDuration,
                    data.hasOverlap,
                    data.startTime,
                    data.endTime
                );
                break;
            case 'cleanup':
                cleanup();
                break;
        }
    } catch (error) {
        self.postMessage({
            type: 'error',
            error: error.message
        });
    }
};

async function loadModel(modelName) {
    if (currentModel === modelName && pipeline) {
        self.postMessage({
            type: 'modelLoaded',
            model: modelName
        });
        return;
    }

    try {
        self.postMessage({
            type: 'progress',
            message: 'Loading Whisper model...',
            percent: 10
        });

        // Use the optimized Xenova/whisper-base model directly
        const modelId = 'Xenova/whisper-base';
        
        pipeline = await self.pipeline('automatic-speech-recognition', modelId, {
            // Optimized for speed and responsiveness
            dtype: {
                encoder_model: 'fp16',
                decoder_model_merged: 'q8'  // Quantized for faster inference
            },
            // Try WebGPU first for acceleration, fall back to CPU
            device: 'webgpu',
            progress_callback: (progress) => {
                if (progress.status === 'downloading') {
                    const percent = Math.round((progress.loaded / progress.total) * 100);
                    self.postMessage({
                        type: 'progress',
                        message: `Downloading model... ${percent}%`,
                        percent: 10 + percent * 0.4
                    });
                }
            }
        });

        currentModel = modelName;
        
        self.postMessage({
            type: 'modelLoaded',
            model: modelName
        });

    } catch (error) {
        console.error('WebGPU model loading failed, trying CPU fallback:', error);
        
        // Fallback to CPU
        try {
            self.postMessage({
                type: 'progress',
                message: 'Loading model (CPU fallback)...',
                percent: 35
            });

            pipeline = await self.pipeline('automatic-speech-recognition', 'Xenova/whisper-base', {
                dtype: {
                    encoder_model: 'fp32',
                    decoder_model_merged: 'q8'
                },
                device: 'cpu',
                progress_callback: (progress) => {
                    if (progress.status === 'downloading') {
                        const percent = Math.round((progress.loaded / progress.total) * 100);
                        self.postMessage({
                            type: 'progress',
                            message: `Downloading model (CPU)... ${percent}%`,
                            percent: 35 + percent * 0.15
                        });
                    }
                }
            });

            currentModel = modelName;
            
            self.postMessage({
                type: 'modelLoaded',
                model: modelName,
                device: 'cpu'
            });

        } catch (fallbackError) {
            throw new Error(`Failed to load model: ${fallbackError.message}`);
        }
    }
}

async function transcribeChunk(audioData, options, chunkIndex, totalChunks, chunkDuration, overlapDuration, hasOverlap, startTime, endTime) {
    if (!pipeline) {
        throw new Error('Model not loaded');
    }

    try {
        self.postMessage({
            type: 'chunkStart',
            chunkIndex,
            totalChunks,
            chunkDuration,
            startTime,
            endTime
        });

        const processingStartTime = Date.now();
        console.log(`Processing Chunk ${chunkIndex + 1}/${totalChunks} from ${startTime}s to ${endTime}s, duration ${chunkDuration}s`);
        
        // Enhanced options for better quality and language consistency
        const enhancedOptions = {
            chunk_length_s: 30, // Use full 30s for internal processing
            stride_length_s: hasOverlap ? 5 : 1, // Adjust stride based on overlap
            return_timestamps: false,
            condition_on_previous_text: false, // Disable to prevent repetition with natural pause chunks
            compression_ratio_threshold: 2.4,
            logprob_threshold: -1.0,
            no_speech_threshold: 0.6,
            // Force language consistency and prevent repetition
            task: 'transcribe', // Explicitly set transcription task
            temperature: 0.0, // Use deterministic decoding to prevent loops
            repetition_penalty: 1.2, // Higher penalty to prevent repetition
            ...options
        };
        
        // Force language consistency - prevent auto-translation
        if (options.language && options.language !== 'auto') {
            enhancedOptions.language = options.language;
            
            // For Chinese and other non-English languages, be more strict
            if (options.language === 'zh' || options.language === 'chinese') {
                // Use additional parameters to enforce Chinese
                enhancedOptions.task = 'transcribe';
                enhancedOptions.temperature = 0.0;
                enhancedOptions.repetition_penalty = 1.3; // Even higher for Chinese
                enhancedOptions.max_length = 448; // Limit length to prevent runaway generation
            }
        }

        const result = await pipeline(audioData, enhancedOptions);
        const processingTime = Date.now() - processingStartTime;
        const text = result.text || result || '';

        self.postMessage({
            type: 'chunkComplete',
            chunkIndex,
            text: text.trim(),
            processingTime,
            totalChunks,
            hasOverlap,
            chunkDuration,
            overlapDuration,
            startTime,
            endTime
        });

    } catch (error) {
        self.postMessage({
            type: 'chunkError',
            chunkIndex,
            error: error.message,
            totalChunks
        });
    }
}

function cleanup() {
    pipeline = null;
    currentModel = null;
    self.postMessage({
        type: 'cleanupComplete'
    });
}
