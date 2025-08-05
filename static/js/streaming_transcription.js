// Updated frontend logic to handle optimized streaming

/**
 * Start transcription from URL without full download
 * @param {string} url - The YouTube URL
 * @param {string} language - Language code
 */
async function startStreamedTranscription(url, language) {
    try {
        // Fetch audio stream URL from server
        const response = await fetch('/transcribe-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, language }),
        });

        const data = await response.json();

        if (!response.ok || data.error) {
            throw new Error(data.error || 'Failed to start transcription');
        }

        if (data.audio_url) {
            console.log('Received audio URL for client-side processing:', data.audio_url);
            // Start client-side streaming transcription (optional)
            if (data.use_client) {
                await transcribeClientSide(data.audio_url, language);
            }
        } else {
            console.log('Server-side transcription started:', data);
            alert('Transcription starting server-side, check server logs');
        }
    } catch (error) {
        console.error('Transcription failed:', error);
        alert(`Error: ${error.message || error}`);
    }
}

/**
 * Example client-side transcription using Web Audio API
 * @param {string} audioUrl - The audio stream URL
 * @param {string} language - Language code
 */
async function transcribeClientSide(audioUrl, language) {
    // This is a placeholder for your Whisper client-side implementation
    const response = await fetch(audioUrl);

    const reader = response.body.getReader();
    let audioBuffer = new Float32Array();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Process value (audio chunk)
        // Convert value (Uint8Array) to Float32Array and append to audioBuffer
        audioBuffer = new Float32Array([...audioBuffer, ...new Float32Array(value.buffer)]);

        // Optionally transcribe part of the buffer with Whisper
        // const transcript = await whisper_transcription_function(audioBuffer, language);

        // Also update UI with progress
    }

    console.log('Client-side transcription complete. Final audio length:', audioBuffer.length / 16000);
    // Display or further process final transcript
}

