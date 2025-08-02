// Web Worker for Whisper Transcription
// This runs in a separate thread to keep the UI responsive

let pipeline = null;
let currentModel = null;
let transformersLoaded = false;

// Load Transformers.js in the worker using dynamic import
async function loadTransformers() {
    try {
        // Try to load the transformers library
        const transformers = await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2/dist/transformers.min.js');
        
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
                await transcribeChunk(data.audioData, data.options, data.chunkIndex, data.totalChunks);
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

async function transcribeChunk(audioData, options, chunkIndex, totalChunks) {
    if (!pipeline) {
        throw new Error('Model not loaded');
    }

    try {
        // Send progress update
        self.postMessage({
            type: 'chunkStart',
            chunkIndex,
            totalChunks
        });

        const startTime = Date.now();
        
        // Transcribe the chunk with optimized settings for speed
        const result = await pipeline(audioData, {
            // Optimized for streaming
            chunk_length_s: 8,  // Smaller chunks for faster processing
            stride_length_s: 1,
            return_timestamps: false,
            ...options
        });

        const processingTime = Date.now() - startTime;
        const text = result.text || result || '';

        // Send result back to main thread
        self.postMessage({
            type: 'chunkComplete',
            chunkIndex,
            text: text.trim(),
            processingTime,
            totalChunks
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
