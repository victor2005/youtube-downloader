#!/usr/bin/env python3
"""
Deployment Test Script for Multilingual YouTube Downloader
Tests that all language endpoints and functionality work correctly.
"""

import requests
import sys
import time
from urllib.parse import urljoin

def test_deployment(base_url):
    """Test the multilingual deployment"""
    print(f"🚀 Testing deployment at: {base_url}")
    print("=" * 50)
    
    # Test 1: Health Check
    print("1️⃣ Testing health endpoint...")
    try:
        response = requests.get(urljoin(base_url, "/health"), timeout=10)
        if response.status_code == 200:
            print("✅ Health check passed")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False
    
    # Test 2: Main page loads
    print("\n2️⃣ Testing main page...")
    try:
        response = requests.get(base_url, timeout=10)
        if response.status_code == 200 and "YouTube Downloader" in response.text:
            print("✅ Main page loads correctly")
        else:
            print(f"❌ Main page failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Main page error: {e}")
        return False
    
    # Test 3: Language switching
    print("\n3️⃣ Testing language switching...")
    languages = [
        ("es", "Descargador de YouTube"),
        ("zh", "YouTube下载器"),
        ("en", "YouTube Downloader")
    ]
    
    session = requests.Session()
    
    for lang_code, expected_title in languages:
        try:
            # Set language
            lang_url = urljoin(base_url, f"/set_language/{lang_code}")
            response = session.get(lang_url, timeout=10)
            
            # Check main page with new language
            response = session.get(base_url, timeout=10)
            if response.status_code == 200 and expected_title in response.text:
                print(f"✅ {lang_code.upper()} language works: '{expected_title}'")
            else:
                print(f"❌ {lang_code.upper()} language failed")
                return False
        except Exception as e:
            print(f"❌ Language {lang_code} error: {e}")
            return False
    
    # Test 4: Check translation files are included
    print("\n4️⃣ Testing translation functionality...")
    try:
        # Test Spanish
        response = session.get(urljoin(base_url, "/set_language/es"), timeout=10)
        response = session.get(base_url, timeout=10)
        
        spanish_terms = ["Formato de Descarga", "Iniciar Descarga", "URL de YouTube"]
        spanish_found = sum(1 for term in spanish_terms if term in response.text)
        
        if spanish_found >= 2:
            print("✅ Spanish translations working")
        else:
            print("⚠️  Spanish translations may be incomplete")
        
        # Test Chinese
        response = session.get(urljoin(base_url, "/set_language/zh"), timeout=10)
        response = session.get(base_url, timeout=10)
        
        chinese_terms = ["下载格式", "开始下载", "YouTube链接"]
        chinese_found = sum(1 for term in chinese_terms if term in response.text)
        
        if chinese_found >= 2:
            print("✅ Chinese translations working")
        else:
            print("⚠️  Chinese translations may be incomplete")
            
    except Exception as e:
        print(f"❌ Translation test error: {e}")
        return False
    
    print("\n🎉 All deployment tests passed!")
    print("🌍 Multilingual YouTube Downloader is successfully deployed!")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_deployment.py <base_url>")
        print("Example: python test_deployment.py https://your-app.railway.app")
        sys.exit(1)
    
    base_url = sys.argv[1].rstrip('/')
    success = test_deployment(base_url)
    sys.exit(0 if success else 1)
