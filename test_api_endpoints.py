#!/usr/bin/env python
"""
Test API Endpoints for Looping Detection
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cn_project.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
import json

def test_api_endpoints():
    """Test all looping detection API endpoints"""
    
    # Create test client
    client = Client()
    
    # Create admin user for authentication
    admin_user, created = User.objects.get_or_create(
        username='admin',
        defaults={'is_staff': True, 'is_superuser': True}
    )
    admin_user.set_password('adminpass')
    admin_user.save()
    
    # Login as admin
    client.login(username='admin', password='adminpass')
    
    print("\n" + "="*90)
    print("  API ENDPOINT TESTS - LOOPING DETECTION".center(90))
    print("="*90 + "\n")
    
    # Test 1: Basic looping detection endpoint
    print("TEST 1: Basic Looping Detection")
    print("-" * 90)
    response = client.get('/admin-panel/api/looping-detection/')
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Success: {data['success']}")
        print(f"  Total Issues: {data['total_issues']}")
        print(f"  Critical Issues: {data['critical_issues']}")
        print(f"  Statistics:")
        print(f"    - Total Requests: {data['statistics']['total_requests']}")
        print(f"    - Unique IPs: {data['statistics']['unique_ips']}")
        print(f"    - Looping Issues: {data['statistics']['looping_issues_detected']}")
    else:
        print(f"✗ Error: {response.content}")
    
    # Test 2: Custom thresholds
    print("\n\nTEST 2: Custom Thresholds")
    print("-" * 90)
    response = client.get('/admin-panel/api/looping-detection/?threshold=10&time_window=15')
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Parameters applied:")
        print(f"  - Request Threshold: {data['threshold']}")
        print(f"  - Time Window: {data['time_window_seconds']}s")
        print(f"  - Issues Found: {data['total_issues']}")
    
    # Test 3: Looping statistics endpoint
    print("\n\nTEST 3: Looping Statistics")
    print("-" * 90)
    response = client.get('/admin-panel/api/looping-statistics/?time_window=600')
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        stats = data['statistics']
        print(f"✓ Statistics retrieved:")
        print(f"  - Total Requests: {stats['total_requests']}")
        print(f"  - Unique IPs: {stats['unique_ips']}")
        print(f"  - Unique Users: {stats['unique_users']}")
        print(f"  - Avg Requests/IP: {stats['average_requests_per_ip']}")
        print(f"  - Looping Issues: {stats['looping_issues_detected']}")
        print(f"  - Critical Issues: {stats['critical_looping_issues']}")
    
    # Test 4: Looping timeline (need active IP)
    print("\n\nTEST 4: Looping Timeline for IP")
    print("-" * 90)
    
    # Get an active IP from request logs
    from network_sim.models import RequestLog
    active_ip = RequestLog.objects.values_list('ip_address', flat=True).first()
    
    if active_ip:
        response = client.get(f'/admin-panel/api/looping-timeline/?ip={active_ip}&limit=120')
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Timeline retrieved for IP: {data['ip_address']}")
            print(f"  - Request Count: {data['request_count']}")
            print(f"  - Time Limit: {data['time_limit_seconds']}s")
            if data['request_count'] > 0:
                print(f"  - Sample Requests:")
                for req in data['timeline'][:3]:
                    print(f"    • {req['method']} {req['path']} -> {req['status_code']}")
        else:
            print(f"✗ Error: {response.content}")
    else:
        print("No request logs found to test timeline")
    
    # Test 5: Unauthenticated access (should fail)
    print("\n\nTEST 5: Security - Unauthenticated Access")
    print("-" * 90)
    
    # Logout
    client.logout()
    
    response = client.get('/admin-panel/api/looping-detection/')
    print(f"Status Code (without auth): {response.status_code}")
    
    if response.status_code == 403:
        print("✓ Correctly rejected unauthenticated request")
    else:
        print(f"⚠ Unexpected status code: {response.status_code}")
    
    print("\n" + "="*90)
    print("  ALL API TESTS COMPLETED".center(90))
    print("="*90 + "\n")

if __name__ == '__main__':
    try:
        test_api_endpoints()
    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
