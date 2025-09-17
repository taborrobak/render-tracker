#!/usr/bin/env python3
"""
Test script to demonstrate full URL generation for deployment
"""
import asyncio
import os
from server import get_job_preview
from fastapi import Request

# Mock request classes for testing
class MockRequest:
    def __init__(self, scheme, netloc):
        self.url = MockURL(scheme, netloc)

class MockURL:
    def __init__(self, scheme, netloc):
        self.scheme = scheme
        self.netloc = netloc

async def test_url_generation():
    print("=== RENDER TRACKER URL GENERATION TEST ===\n")
    
    # Test scenarios
    scenarios = [
        ("Local Development", "http", "localhost:8000"),
        ("Railway Production", "https", "render-tracker-production.up.railway.app"),
        ("Custom Domain", "https", "render.mycompany.com"),
    ]
    
    for name, scheme, netloc in scenarios:
        print(f"🌐 {name}:")
        request = MockRequest(scheme, netloc)
        result = await get_job_preview(1, request)
        
        print(f"   Base URL: {scheme}://{netloc}")
        print(f"   Image URL: {result['image_url']}")
        print(f"   Link Display: 🔗 {result['image_url']}")
        print()
    
    print("✅ All URL generation tests completed!")
    print("\n💡 For Railway deployment:")
    print("   • The system automatically detects Railway environment variables")
    print("   • RAILWAY_PUBLIC_DOMAIN or RAILWAY_STATIC_URL will be used")
    print("   • Workers can use these full URLs to access images")
    print("   • Frontend displays full URLs for easy copying")

if __name__ == "__main__":
    asyncio.run(test_url_generation())
