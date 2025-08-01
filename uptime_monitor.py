#!/usr/bin/env python3
"""
Simple uptime monitor to prevent Railway cold starts
Run this on a separate server or use a service like UptimeRobot
"""

import requests
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Your website URL
WEBSITE_URL = "https://ytdownl.xyz/ping"
CHECK_INTERVAL = 300  # 5 minutes

def ping_website():
    """Ping the website to keep it warm"""
    try:
        response = requests.get(WEBSITE_URL, timeout=10)
        if response.status_code == 200:
            logging.info(f"✅ Website is up - Response time: {response.elapsed.total_seconds():.2f}s")
            return True
        else:
            logging.warning(f"⚠️ Website returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Failed to reach website: {e}")
        return False

def main():
    """Main monitoring loop"""
    logging.info(f"🚀 Starting uptime monitor for {WEBSITE_URL}")
    logging.info(f"📊 Checking every {CHECK_INTERVAL} seconds")
    
    while True:
        ping_website()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
