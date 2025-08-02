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
    downloadBtn.textContent = window.i18n.startingDownload;
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
            throw new Error(data.error || window.i18n.downloadFailed);
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
            const response = await fetch(`/progress/${downloadId}?t=${Date.now()}`);
            const progress = await response.json();
            
            console.log('Checking progress:', progress);
            
            if (progress.status === 'downloading') {
                progressText.textContent = `${window.i18n.downloadingProgress} ${progress.percent} (${progress.speed})`;
                const percentMatch = progress.percent.match(/(\d+\.?\d*)%/);
                if (percentMatch) {
                    progressFill.style.width = percentMatch[1] + '%';
                }
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'initializing') {
                progressText.textContent = window.i18n.initializingDownload;
                progressFill.style.width = '5%';
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'preparing') {
                progressText.textContent = window.i18n.preparingDownload;
                progressFill.style.width = '15%';
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'starting') {
                progressText.textContent = progress.message || window.i18n.startingDownloadMsg;
                progressFill.style.width = '25%';
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'processing') {
                progressText.textContent = progress.message || window.i18n.processingFiles;
                progressFill.style.width = '85%';
                setTimeout(checkProgress, 1000);
            } else if (progress.status === 'converting') {
                progressText.textContent = window.i18n.convertingToMP3;
                progressFill.style.width = '90%';
                setTimeout(checkProgress, 2000); // Check less frequently during conversion
            } else if (progress.status === 'finished') {
                console.log('Download finished, updating UI and refreshing downloads list');
                progressFill.style.width = '100%';
                progressText.textContent = window.i18n.fileReadyForDownload;
                document.getElementById('successMessage').textContent = window.i18n.fileConvertedReady;
                document.getElementById('successMessage').style.display = 'block';
                resetForm();
                
                // Check if Safari - only add delay for Safari
                const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
                const initialDelay = isSafari ? 1500 : 1000; // 1.5 second delay for Safari, 1s for others
                
                // Refresh downloads list with Safari-specific delay
                setTimeout(() => {
                    console.log('Triggering downloads list refresh');
                    loadDownloads();
                }, initialDelay);
                
                // Follow-up refreshes for both browsers
                setTimeout(() => {
                    console.log('Triggering delayed downloads list refresh (2s)');
                    loadDownloads();
                }, 2000 + initialDelay);
                setTimeout(() => {
                    console.log('Triggering final downloads list refresh (5s)');
                    loadDownloads();
                }, 5000 + initialDelay);
            } else if (progress.status === 'error') {
                throw new Error(progress.error);
            } else if (progress.status === 'not_found') {
                console.log('Download ID not found, stopping progress check');
                document.getElementById('errorMessage').textContent = window.i18n.downloadSessionExpired;
                document.getElementById('errorMessage').style.display = 'block';
                resetForm();
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
    document.getElementById('downloadBtn').textContent = window.i18n.startDownload;
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
        const timestamp = new Date().toISOString();
        console.log(`[${timestamp}] Loading downloads...`);
        const response = await fetch('/downloads?t=' + Date.now());
        const files = await response.json();
        console.log(`[${timestamp}] Downloads API response:`, files);
        const downloadsList = document.getElementById('downloadsList');
        
        downloadsList.innerHTML = '';
        
        if (files.length === 0) {
            console.log(`[${timestamp}] No files found, showing empty message`);
            downloadsList.innerHTML = `<li style="text-align: center; color: #666; padding: 20px;">${window.i18n.noDownloadsYet}</li>`;
        } else {
            console.log(`[${timestamp}] Displaying ${files.length} files:`, files.map(f => f.name));
            files.forEach(file => {
                const li = document.createElement('li');
                li.className = 'download-item';
                li.innerHTML = `
                    <div class="download-item-info">
                        <div class="download-item-name">${file.name}</div>
                        <div class="download-item-size">${formatFileSize(file.size)}</div>
                    </div>
                    <a href="/download-file/${encodeURIComponent(file.name)}" class="download-link">${window.i18n.download}</a>
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
