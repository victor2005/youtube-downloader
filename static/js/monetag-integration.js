// Monetag Ad Integration - Targeted Triggers Only
// This script manages ad triggers for specific user actions

(function() {
    'use strict';
    
    // Configuration
    const AD_CONFIG = {
        enabled: true,
        debugMode: false, // Set to true to see console logs
        cooldownTime: 60000, // 60 seconds between ads
        triggers: {
            'file_download': true,
            'transcription_copy': true,
            'transcription_download': true,
            'transcription_interact': true
        }
    };
    
    // Track last ad trigger time
    let lastAdTriggerTime = 0;
    
    // Function to check if ad should be triggered
    function shouldTriggerAd(eventType) {
        if (!AD_CONFIG.enabled) return false;
        if (!AD_CONFIG.triggers[eventType]) return false;
        
        const now = Date.now();
        if (now - lastAdTriggerTime < AD_CONFIG.cooldownTime) {
            if (AD_CONFIG.debugMode) {
                console.log(`Ad cooldown active. Time remaining: ${Math.ceil((AD_CONFIG.cooldownTime - (now - lastAdTriggerTime)) / 1000)}s`);
            }
            return false;
        }
        
        return true;
    }
    
    // Main ad trigger function
    window.monetagAdTrigger = function(eventType) {
        if (AD_CONFIG.debugMode) {
            console.log(`Ad trigger called for event: ${eventType}`);
        }
        
        if (!shouldTriggerAd(eventType)) {
            return;
        }
        
        try {
            // Update last trigger time
            lastAdTriggerTime = Date.now();
            
            // ========================================
            // MONETAG ONCLICK INTEGRATION
            // ========================================
            
            // Open Monetag link in a new window (popunder style)
            const adWindow = window.open('https://otieu.com/4/9679323', '_blank');
            
            // Try to focus back on the original window (popunder behavior)
            if (adWindow) {
                adWindow.blur();
                window.focus();
            }
            
            if (AD_CONFIG.debugMode) {
                console.log(`✓ Ad triggered for: ${eventType}`);
                console.log('Next ad available in:', AD_CONFIG.cooldownTime / 1000, 'seconds');
            }
            
        } catch (error) {
            if (AD_CONFIG.debugMode) {
                console.error('Error triggering ad:', error);
            }
        }
    };
    
    // Optional: Track page visibility to pause cooldown when tab is not active
    let hiddenTime = 0;
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            hiddenTime = Date.now();
        } else if (hiddenTime > 0) {
            // Extend cooldown by the time the tab was hidden
            const hiddenDuration = Date.now() - hiddenTime;
            lastAdTriggerTime += hiddenDuration;
            hiddenTime = 0;
        }
    });
    
    // Log initialization
    if (AD_CONFIG.debugMode) {
        console.log('Monetag integration initialized with config:', AD_CONFIG);
    }
})();
