document.querySelectorAll('.format-option').forEach(option => {
    option.addEventListener('click', () => {
        document.querySelectorAll('.format-option').forEach(opt => opt.classList.remove('selected'));
        option.classList.add('selected');
        option.querySelector('input[type="radio"]').checked = true;
    });
});

document.getElementById('downloadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const url = document.getElementById('url').value;
    const format = document.querySelector('input[name="format"]:checked').value;
    const downloadBtn = document.getElementById('downloadBtn');
    const errorMessage = document.getElementById('errorMessage');
    const successMessage = document.getElementById('successMessage');
    const progressSection = document.getElementById('progressSection');
    
    errorMessage.style.display = 'none';
    successMessage.style.display = 'none';
    
    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Starting Download...';
    progressSection.style.display = 'block';
    startAutoRefresh(); // Start auto-refreshing the download list
    
    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ url, format })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            monitorProgress(data.download_id);
        } else {
            throw new Error(data.error || 'Download failed');
        }
    } catch (error) {
        errorMessage.textContent = error.message;
        errorMessage.style.display = 'block';
        resetForm();
    }
});

function monitorProgress(downloadId) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    
    const checkProgress = async () => {
        try {
            const response = await fetch(`/progress/${downloadId}`);
            const progress = await response.json();
            
            if (progress.status === 'downloading') {
                progressText.textContent = `Downloading... ${progress.percent} (${progress.speed})`;
                const percentMatch = progress.percent.match(/(\d+\.?\d*)%/);
                if (percentMatch) {
                    progressFill.style.width = percentMatch[1] + '%';
                }
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'initializing') {
                progressText.textContent = 'Initializing download...';
                progressFill.style.width = '10%';
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'preparing') {
                progressText.textContent = 'Preparing download...';
                progressFill.style.width = '20%';
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'converting') {
                progressText.textContent = progress.message || 'Converting to MP3...';
                progressFill.style.width = '90%';
                setTimeout(checkProgress, 2000); // Check less frequently during conversion
            } else if (progress.status === 'finished') {
                progressFill.style.width = '100%';
                progressText.textContent = 'Download completed!';
                document.getElementById('successMessage').textContent = 'Download completed successfully!';
                document.getElementById('successMessage').style.display = 'block';
                resetForm();
                // Refresh download list after a short delay to ensure file is processed
                setTimeout(loadDownloads, 1000);
            } else if (progress.status === 'error') {
                throw new Error(progress.error);
            } else {
                setTimeout(checkProgress, 1000);
            }
        } catch (error) {
            document.getElementById('errorMessage').textContent = error.message;
            document.getElementById('errorMessage').style.display = 'block';
            resetForm();
        }
    };
    
    checkProgress();
}

function resetForm() {
    document.getElementById('downloadBtn').disabled = false;
    document.getElementById('downloadBtn').textContent = 'Start Download';
    document.getElementById('progressSection').style.display = 'none';
    document.getElementById('progressFill').style.width = '0%';
    stopAutoRefresh(); // Stop auto-refreshing when download is done
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

async function loadDownloads() {
    try {
        const response = await fetch('/downloads');
        const files = await response.json();
        const downloadsList = document.getElementById('downloadsList');
        
        downloadsList.innerHTML = '';
        
        if (files.length === 0) {
            downloadsList.innerHTML = '<li style="text-align: center; color: #666; padding: 20px;">No downloads yet</li>';
        } else {
            files.forEach(file => {
                const li = document.createElement('li');
                li.className = 'download-item';
                li.innerHTML = `
                    <div class="download-item-info">
                        <div class="download-item-name">${file.name}</div>
                        <div class="download-item-size">${formatFileSize(file.size)}</div>
                    </div>
                    <a href="/download-file/${encodeURIComponent(file.name)}" class="download-link">Download</a>
                `;
                downloadsList.appendChild(li);
            });
        }
    } catch (error) {
        console.error('Failed to load downloads:', error);
    }
}

// Auto-refresh downloads list every 5 seconds when there's an active download
let autoRefreshInterval = null;

function startAutoRefresh() {
    if (autoRefreshInterval) return; // Already running
    autoRefreshInterval = setInterval(loadDownloads, 5000);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

loadDownloads();
