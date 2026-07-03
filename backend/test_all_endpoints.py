"""
Comprehensive API endpoint testing script based on Postman collection.
Tests all endpoints to ensure they work for users who aren't currently flying.
"""

import httpx
import json
import asyncio
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

class APITester:
    def __init__(self):
        self.client = httpx.Client()
        self.access_token = None
        self.refresh_token = None
        self.user_id = None
        self.route_key = None
        self.poi_source_id = None
        self.content_job_id = None
        
    def print_result(self, test_name: str, success: bool, details: str = ""):
        """Print test result with formatting."""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        if details:
            print(f"     {details}")
    
    def test_health_check(self):
        """Test health check endpoint."""
        try:
            response = self.client.get(f"{BASE_URL}/health")
            success = response.status_code == 200
            self.print_result("Health Check", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Health Check", False, f"Error: {str(e)}")
            return False
    
    def test_register_user(self):
        """Test user registration."""
        try:
            user_data = {
                "email": "test_user_non_flying@example.com",
                "password": "TestPassword123!",
                "full_name": "Test Non-Flying User"
            }
            response = self.client.post(f"{BASE_URL}/v1/auth/register", json=user_data)
            success = response.status_code in [200, 201, 400]  # 400 if user already exists
            if success:
                data = response.json()
                if response.status_code in [200, 201]:
                    self.user_id = data.get("id")
            self.print_result("User Registration", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("User Registration", False, f"Error: {str(e)}")
            return False
    
    def test_login(self):
        """Test user login."""
        try:
            login_data = {
                "email": "test_user_non_flying@example.com",
                "password": "TestPassword123!"
            }
            response = self.client.post(f"{BASE_URL}/v1/auth/login", json=login_data)
            success = response.status_code == 200
            if success:
                data = response.json()
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})
            self.print_result("User Login", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("User Login", False, f"Error: {str(e)}")
            return False
    
    def test_get_airports(self):
        """Test getting airports (ground-based user planning a trip)."""
        try:
            response = self.client.get(f"{BASE_URL}/v1/airports")
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     Found {len(data)} airports")
            self.print_result("Get Airports", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Get Airports", False, f"Error: {str(e)}")
            return False
    
    def test_search_airports(self):
        """Test airport search."""
        try:
            response = self.client.get(f"{BASE_URL}/v1/airports/search?query=Dubai")
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     Found {len(data)} airports matching 'Dubai'")
            self.print_result("Search Airports", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Search Airports", False, f"Error: {str(e)}")
            return False
    
    def test_get_airport_by_code(self):
        """Test getting specific airport by code."""
        try:
            response = self.client.get(f"{BASE_URL}/v1/airports/DXB")
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     Airport: {data.get('name', 'N/A')}")
            self.print_result("Get Airport by Code (DXB)", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Get Airport by Code (DXB)", False, f"Error: {str(e)}")
            return False
    
    def test_create_route(self):
        """Test creating a route (ground-based user planning)."""
        try:
            route_data = {
                "origin_airport_code": "ADD",
                "destination_airport_code": "DXB",
                "poi_source_ids": ["wikipedia:1001", "wikipedia:1002"]
            }
            response = self.client.post(f"{BASE_URL}/v1/routes", json=route_data)
            success = response.status_code == 200
            if success:
                data = response.json()
                self.route_key = data.get("route_key")
                print(f"     Created route: {self.route_key}")
            self.print_result("Create Route", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Create Route", False, f"Error: {str(e)}")
            return False
    
    def test_get_route(self):
        """Test getting route details."""
        if not self.route_key:
            self.print_result("Get Route", False, "No route_key available")
            return False
            
        try:
            response = self.client.get(f"{BASE_URL}/v1/routes/{self.route_key}")
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     Route: {data.get('origin', 'N/A')} -> {data.get('destination', 'N/A')}")
            self.print_result("Get Route", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Get Route", False, f"Error: {str(e)}")
            return False
    
    def test_search_pois(self):
        """Test POI search (ground-based user exploring destinations)."""
        try:
            response = self.client.get(f"{BASE_URL}/v1/pois/search?query=burj+khalifa")
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     Found {len(data.get('pois', []))} POIs")
                if data.get('pois'):
                    self.poi_source_id = data['pois'][0].get('source_id')
            self.print_result("Search POIs", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Search POIs", False, f"Error: {str(e)}")
            return False
    
    def test_get_poi_details(self):
        """Test getting POI details."""
        if not self.poi_source_id:
            self.print_result("Get POI Details", False, "No poi_source_id available")
            return False
            
        try:
            response = self.client.get(f"{BASE_URL}/v1/pois/{self.poi_source_id}")
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     POI: {data.get('name', 'N/A')}")
            self.print_result("Get POI Details", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Get POI Details", False, f"Error: {str(e)}")
            return False
    
    def test_start_content_generation(self):
        """Test starting content generation (new async endpoint)."""
        if not self.route_key:
            self.print_result("Start Content Generation", False, "No route_key available")
            return False
            
        try:
            response = self.client.post(f"{BASE_URL}/v1/routes/{self.route_key}/content")
            success = response.status_code == 200
            if success:
                data = response.json()
                self.content_job_id = data.get("job_id")
                print(f"     Job ID: {self.content_job_id}")
                print(f"     Total POIs: {data.get('total_pois', 'N/A')}")
            self.print_result("Start Content Generation", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Start Content Generation", False, f"Error: {str(e)}")
            return False
    
    def test_get_content_status(self):
        """Test getting content generation status."""
        if not self.route_key or not self.content_job_id:
            self.print_result("Get Content Status", False, "No route_key or job_id available")
            return False
            
        try:
            response = self.client.get(
                f"{BASE_URL}/v1/routes/{self.route_key}/content/status",
                params={"job_id": self.content_job_id}
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     Status: {data.get('status', 'N/A')}")
                print(f"     Progress: {data.get('progress_percent', 0)}%")
            self.print_result("Get Content Status", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Get Content Status", False, f"Error: {str(e)}")
            return False
    
    def test_get_user_profile(self):
        """Test getting user profile."""
        try:
            response = self.client.get(f"{BASE_URL}/v1/users/me")
            success = response.status_code == 200
            if success:
                data = response.json()
                print(f"     User: {data.get('full_name', 'N/A')}")
            self.print_result("Get User Profile", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Get User Profile", False, f"Error: {str(e)}")
            return False
    
    def test_refresh_token(self):
        """Test token refresh."""
        if not self.refresh_token:
            self.print_result("Refresh Token", False, "No refresh_token available")
            return False
            
        try:
            response = self.client.post(
                f"{BASE_URL}/v1/auth/refresh",
                json={"refresh_token": self.refresh_token}
            )
            success = response.status_code == 200
            if success:
                data = response.json()
                self.access_token = data.get("access_token")
                self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})
            self.print_result("Refresh Token", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("Refresh Token", False, f"Error: {str(e)}")
            return False
    
    def test_logout(self):
        """Test user logout."""
        try:
            response = self.client.post(f"{BASE_URL}/v1/auth/logout")
            success = response.status_code == 200
            self.print_result("User Logout", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.print_result("User Logout", False, f"Error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all API tests in sequence."""
        print("=" * 60)
        print("API Endpoint Testing for Non-Flying Users")
        print("=" * 60)
        print()
        
        results = []
        
        # Test 1: Health Check
        results.append(self.test_health_check())
        print()
        
        # Test 2: User Registration
        results.append(self.test_register_user())
        print()
        
        # Test 3: User Login
        results.append(self.test_login())
        print()
        
        # Test 4: Get Airports (trip planning)
        results.append(self.test_get_airports())
        print()
        
        # Test 5: Search Airports
        results.append(self.test_search_airports())
        print()
        
        # Test 6: Get Airport by Code
        results.append(self.test_get_airport_by_code())
        print()
        
        # Test 7: Create Route (trip planning)
        results.append(self.test_create_route())
        print()
        
        # Test 8: Get Route Details
        results.append(self.test_get_route())
        print()
        
        # Test 9: Search POIs (destination exploration)
        results.append(self.test_search_pois())
        print()
        
        # Test 10: Get POI Details
        results.append(self.test_get_poi_details())
        print()
        
        # Test 11: Start Content Generation (new async endpoint)
        results.append(self.test_start_content_generation())
        print()
        
        # Test 12: Get Content Status
        results.append(self.test_get_content_status())
        print()
        
        # Test 13: Get User Profile
        results.append(self.test_get_user_profile())
        print()
        
        # Test 14: Refresh Token
        results.append(self.test_refresh_token())
        print()
        
        # Test 15: Logout
        results.append(self.test_logout())
        print()
        
        # Summary
        print("=" * 60)
        print("Test Summary")
        print("=" * 60)
        total = len(results)
        passed = sum(results)
        failed = total - passed
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        print("=" * 60)
        
        return passed == total

if __name__ == "__main__":
    tester = APITester()
    success = tester.run_all_tests()
    exit(0 if success else 1)
