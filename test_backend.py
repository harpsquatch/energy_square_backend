#!/usr/bin/env python3
"""
Simple Backend Test Script
Run this to test if your backend is working correctly
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoint(endpoint, description):
    """Test a single endpoint"""
    try:
        print(f"\n🧪 Testing: {description}")
        print(f"   URL: {BASE_URL}{endpoint}")
        
        response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Success: {len(str(data))} characters returned")
            return True
        else:
            print(f"   ❌ Failed: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection Error: Backend not running on {BASE_URL}")
        return False
    except requests.exceptions.Timeout:
        print(f"   ❌ Timeout: Backend took too long to respond")
        return False
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False

def main():
    print("🚀 Energy Square Backend Test")
    print("=" * 40)
    
    # Test basic endpoints first
    tests = [
        ("/", "Root endpoint"),
        ("/health", "Health check"),
        ("/api/analytics/debug", "Debug endpoint"),
        ("/api/analytics/test-community", "Community test endpoint"),
        ("/api/analytics/presentation/dashboard", "Dashboard data"),
        ("/api/analytics/presentation/community-dashboard", "Community dashboard"),
        ("/api/analytics/presentation/marketplace", "Marketplace data"),
    ]
    
    passed = 0
    total = len(tests)
    
    for endpoint, description in tests:
        if test_endpoint(endpoint, description):
            passed += 1
    
    print(f"\n📋 Test Results")
    print(f"=" * 20)
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == 0:
        print(f"\n⚠️  Backend is not responding!")
        print(f"   Make sure to:")
        print(f"   1. Start backend: cd be && python -m app.main")
        print(f"   2. Check MongoDB is running")
        print(f"   3. Create be/.env file")
    elif passed < total:
        print(f"\n⚠️  Some endpoints failed")
        print(f"   Check backend logs for errors")
    else:
        print(f"\n🎉 All tests passed! Backend is ready.")

if __name__ == "__main__":
    main()
