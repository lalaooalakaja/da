"""
Backend API Testing for Procurement Portal (Portal Pengadaan)
Testing Phase 2 - Portal Pengadaan end-to-end
"""
import requests
import sys
import json
from datetime import datetime

BASE_URL = "https://procurement-portal-36.preview.emergentagent.com"

class ProcurementPortalTester:
    def __init__(self):
        self.tokens = {}  # Store tokens for different users
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.material_id = None  # Will be fetched for price-lookup test

    def log_test(self, name, passed, details=""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n{status} - {name}")
        if details:
            print(f"  Details: {details}")
        self.test_results.append({
            "test": name,
            "passed": passed,
            "details": details
        })

    def login(self, email, password, label=""):
        """Login and get token"""
        print(f"\n{'='*70}")
        print(f"LOGGING IN: {label or email}")
        print('='*70)
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get('token')
                if token:
                    self.tokens[email] = token
                    print(f"✅ Login successful - Token: {token[:20]}...")
                    return True
                else:
                    print(f"❌ Login failed - No token in response")
                    return False
            else:
                print(f"❌ Login failed - Status: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False

    def get_headers(self, email="admin@garment.com"):
        """Get request headers with auth token"""
        token = self.tokens.get(email)
        if not token:
            return {"Content-Type": "application/json"}
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

    def test_procurement_overview(self):
        """Test GET /api/procurement/overview"""
        print(f"\n{'='*70}")
        print("TEST 1: Procurement Overview API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/overview",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Overview API returns 200", False, f"Got {response.status_code}: {response.text}")
                return False
            
            self.log_test("Overview API returns 200", True)
            
            data = response.json()
            
            # Check required fields
            if 'kpi' not in data:
                self.log_test("Overview has 'kpi' field", False)
                return False
            self.log_test("Overview has 'kpi' field", True)
            
            kpi = data['kpi']
            
            # Check KPI fields
            kpi_fields = ['suppliers_total', 'suppliers_active', 'po_open', 'po_value_this_month']
            for field in kpi_fields:
                if field in kpi:
                    self.log_test(f"KPI has '{field}'", True, f"Value: {kpi[field]}")
                else:
                    self.log_test(f"KPI has '{field}'", False)
            
            # Validate POC data: 4 suppliers, 1 PO open, value Rp 1.850.000
            if kpi.get('suppliers_active') == 4:
                self.log_test("Suppliers active = 4 (POC data)", True)
            else:
                self.log_test("Suppliers active = 4 (POC data)", False, f"Got {kpi.get('suppliers_active')}")
            
            if kpi.get('po_open') >= 1:
                self.log_test("PO open >= 1 (POC data)", True, f"Got {kpi.get('po_open')}")
            else:
                self.log_test("PO open >= 1 (POC data)", False, f"Got {kpi.get('po_open')}")
            
            # Check for value around 1.850.000 (allow some variance)
            po_value = kpi.get('open_po_value', 0)
            if 1800000 <= po_value <= 1900000:
                self.log_test("Open PO value ~Rp 1.850.000 (POC data)", True, f"Got Rp {po_value:,.0f}")
            else:
                self.log_test("Open PO value ~Rp 1.850.000 (POC data)", False, f"Got Rp {po_value:,.0f}")
            
            return True
            
        except Exception as e:
            self.log_test("Overview API test", False, f"Error: {str(e)}")
            return False

    def test_procurement_pipeline(self):
        """Test GET /api/procurement/pipeline"""
        print(f"\n{'='*70}")
        print("TEST 2: Procurement Pipeline API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/pipeline",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Pipeline API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Pipeline API returns 200", True)
            
            data = response.json()
            
            # Check required fields
            required = ['period_days', 'requests', 'purchase_orders', 'goods_receipts', 'ap_invoices']
            for field in required:
                if field in data:
                    self.log_test(f"Pipeline has '{field}'", True)
                else:
                    self.log_test(f"Pipeline has '{field}'", False)
            
            return True
            
        except Exception as e:
            self.log_test("Pipeline API test", False, f"Error: {str(e)}")
            return False

    def test_spend_analysis(self):
        """Test GET /api/procurement/spend-analysis?months=6"""
        print(f"\n{'='*70}")
        print("TEST 3: Spend Analysis API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/spend-analysis?months=6",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Spend Analysis API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Spend Analysis API returns 200", True)
            
            data = response.json()
            
            # Check required fields
            required = ['months', 'total_value', 'po_count', 'by_supplier', 'by_category', 'by_month', 'top_materials']
            for field in required:
                if field in data:
                    self.log_test(f"Spend Analysis has '{field}'", True)
                else:
                    self.log_test(f"Spend Analysis has '{field}'", False)
            
            # Check total value around 1.850.000
            total_value = data.get('total_value', 0)
            if 1800000 <= total_value <= 1900000:
                self.log_test("Total spend ~Rp 1.850.000 (POC data)", True, f"Got Rp {total_value:,.0f}")
            else:
                self.log_test("Total spend ~Rp 1.850.000 (POC data)", False, f"Got Rp {total_value:,.0f}")
            
            return True
            
        except Exception as e:
            self.log_test("Spend Analysis API test", False, f"Error: {str(e)}")
            return False

    def test_suppliers_list(self):
        """Test GET /api/procurement/suppliers"""
        print(f"\n{'='*70}")
        print("TEST 4: Suppliers List API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/suppliers",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Suppliers List API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Suppliers List API returns 200", True)
            
            data = response.json()
            
            # Check structure
            if 'items' not in data:
                self.log_test("Suppliers has 'items'", False)
                return False
            self.log_test("Suppliers has 'items'", True)
            
            items = data['items']
            
            # Check for 4 suppliers (SUP-0001 to SUP-0004)
            if len(items) >= 4:
                self.log_test("Suppliers count >= 4 (POC data)", True, f"Got {len(items)}")
            else:
                self.log_test("Suppliers count >= 4 (POC data)", False, f"Got {len(items)}")
            
            # Check supplier codes
            codes = [s.get('code') for s in items]
            expected_codes = ['SUP-0001', 'SUP-0002', 'SUP-0003', 'SUP-0004']
            found_codes = [c for c in expected_codes if c in codes]
            if len(found_codes) == 4:
                self.log_test("All 4 POC suppliers present (SUP-0001..0004)", True, f"Found: {', '.join(found_codes)}")
            else:
                self.log_test("All 4 POC suppliers present (SUP-0001..0004)", False, f"Found only: {', '.join(found_codes)}")
            
            return True
            
        except Exception as e:
            self.log_test("Suppliers List API test", False, f"Error: {str(e)}")
            return False

    def test_suppliers_meta(self):
        """Test GET /api/procurement/suppliers/meta"""
        print(f"\n{'='*70}")
        print("TEST 5: Suppliers Meta API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/suppliers/meta",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Suppliers Meta API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Suppliers Meta API returns 200", True)
            
            data = response.json()
            
            # Check required fields
            required = ['payment_terms', 'categories', 'currencies', 'tax_types']
            for field in required:
                if field in data:
                    self.log_test(f"Meta has '{field}'", True)
                else:
                    self.log_test(f"Meta has '{field}'", False)
            
            return True
            
        except Exception as e:
            self.log_test("Suppliers Meta API test", False, f"Error: {str(e)}")
            return False

    def test_suppliers_options(self):
        """Test GET /api/procurement/suppliers/options"""
        print(f"\n{'='*70}")
        print("TEST 6: Suppliers Options API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/suppliers/options",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Suppliers Options API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Suppliers Options API returns 200", True)
            
            data = response.json()
            
            if 'items' not in data:
                self.log_test("Options has 'items'", False)
                return False
            self.log_test("Options has 'items'", True)
            
            items = data['items']
            if len(items) >= 4:
                self.log_test("Options count >= 4", True, f"Got {len(items)}")
            else:
                self.log_test("Options count >= 4", False, f"Got {len(items)}")
            
            return True
            
        except Exception as e:
            self.log_test("Suppliers Options API test", False, f"Error: {str(e)}")
            return False

    def test_supplier_scorecard(self):
        """Test GET /api/procurement/supplier-scorecard?period_days=90"""
        print(f"\n{'='*70}")
        print("TEST 7: Supplier Scorecard API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/supplier-scorecard?period_days=90",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Scorecard API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Scorecard API returns 200", True)
            
            data = response.json()
            
            # Check structure
            required = ['items', 'period_days', 'summary']
            for field in required:
                if field in data:
                    self.log_test(f"Scorecard has '{field}'", True)
                else:
                    self.log_test(f"Scorecard has '{field}'", False)
            
            # Check summary
            if 'summary' in data:
                summary = data['summary']
                if 'suppliers' in summary and 'linked' in summary:
                    self.log_test("Scorecard summary has suppliers count", True, 
                                f"Total: {summary.get('suppliers')}, Linked: {summary.get('linked')}")
                else:
                    self.log_test("Scorecard summary has suppliers count", False)
            
            return True
            
        except Exception as e:
            self.log_test("Scorecard API test", False, f"Error: {str(e)}")
            return False

    def test_migrate_preview(self):
        """Test GET /api/procurement/suppliers/migrate/preview"""
        print(f"\n{'='*70}")
        print("TEST 8: Migration Preview API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/suppliers/migrate/preview",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Migration Preview API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Migration Preview API returns 200", True)
            
            data = response.json()
            
            # Check structure
            required = ['to_create', 'already_matched', 'summary']
            for field in required:
                if field in data:
                    self.log_test(f"Migration preview has '{field}'", True)
                else:
                    self.log_test(f"Migration preview has '{field}'", False)
            
            return True
            
        except Exception as e:
            self.log_test("Migration Preview API test", False, f"Error: {str(e)}")
            return False

    def test_price_lookup(self):
        """Test GET /api/procurement/price-lookup?material_id=<id>"""
        print(f"\n{'='*70}")
        print("TEST 9: Price Lookup API")
        print('='*70)
        
        # First, get a material ID
        try:
            response = requests.get(
                f"{BASE_URL}/api/rahaza/materials?limit=1",
                headers=self.get_headers(),
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                if items:
                    self.material_id = items[0].get('id')
                    print(f"  Using material_id: {self.material_id}")
        except Exception as e:
            print(f"  Warning: Could not fetch material ID: {e}")
        
        if not self.material_id:
            self.log_test("Price Lookup API test", False, "No material_id available")
            return False
        
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/price-lookup?material_id={self.material_id}",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Price Lookup API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Price Lookup API returns 200", True)
            
            data = response.json()
            
            # Check structure
            if 'items' in data:
                self.log_test("Price Lookup has 'items'", True, f"Found {len(data['items'])} price entries")
            else:
                self.log_test("Price Lookup has 'items'", False)
            
            return True
            
        except Exception as e:
            self.log_test("Price Lookup API test", False, f"Error: {str(e)}")
            return False

    def test_purchase_orders(self):
        """Test GET /api/rahaza/purchase-orders"""
        print(f"\n{'='*70}")
        print("TEST 10: Purchase Orders API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/rahaza/purchase-orders",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Purchase Orders API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Purchase Orders API returns 200", True)
            
            data = response.json()
            
            if 'items' in data:
                items = data['items']
                self.log_test("Purchase Orders has 'items'", True, f"Found {len(items)} POs")
                
                # Check for POC PO
                po_numbers = [po.get('po_number') for po in items]
                if 'PO-20260806-001' in po_numbers or 'PO-20260806-002' in po_numbers:
                    self.log_test("Found POC PO (PO-20260806-001 or 002)", True)
                else:
                    self.log_test("Found POC PO (PO-20260806-001 or 002)", False, f"Found: {', '.join(po_numbers[:5])}")
            else:
                self.log_test("Purchase Orders has 'items'", False)
            
            return True
            
        except Exception as e:
            self.log_test("Purchase Orders API test", False, f"Error: {str(e)}")
            return False

    def test_3way_match(self):
        """Test GET /api/rahaza/3way-match"""
        print(f"\n{'='*70}")
        print("TEST 11: 3-Way Match API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/rahaza/3way-match",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("3-Way Match API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("3-Way Match API returns 200", True)
            
            data = response.json()
            
            if 'items' in data or 'summary' in data:
                self.log_test("3-Way Match has data structure", True)
            else:
                self.log_test("3-Way Match has data structure", False)
            
            return True
            
        except Exception as e:
            self.log_test("3-Way Match API test", False, f"Error: {str(e)}")
            return False

    def test_available_for_invoice(self):
        """Test GET /api/rahaza/grs/available-for-invoice"""
        print(f"\n{'='*70}")
        print("TEST 12: Available for Invoice API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/rahaza/grs/available-for-invoice",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Available for Invoice API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Available for Invoice API returns 200", True)
            
            data = response.json()
            
            if 'items' in data:
                self.log_test("Available for Invoice has 'items'", True, f"Found {len(data['items'])} items")
            else:
                self.log_test("Available for Invoice has 'items'", False)
            
            return True
            
        except Exception as e:
            self.log_test("Available for Invoice API test", False, f"Error: {str(e)}")
            return False

    def test_notification_categories(self):
        """Test GET /api/notifications/categories - must have 'procurement' category"""
        print(f"\n{'='*70}")
        print("TEST 13: Notification Categories API")
        print('='*70)
        try:
            response = requests.get(
                f"{BASE_URL}/api/notifications/categories",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Notification Categories API returns 200", False, f"Got {response.status_code}")
                return False
            
            self.log_test("Notification Categories API returns 200", True)
            
            data = response.json()
            
            if 'categories' in data:
                categories = data['categories']
                self.log_test("Has 'categories' field", True)
                
                # Check for procurement category
                proc_cat = None
                for cat in categories:
                    if cat.get('key') == 'procurement':
                        proc_cat = cat
                        break
                
                if proc_cat:
                    self.log_test("Has 'procurement' category", True, f"Label: {proc_cat.get('label')}")
                    if proc_cat.get('label') == 'Pengadaan':
                        self.log_test("Procurement category label is 'Pengadaan'", True)
                    else:
                        self.log_test("Procurement category label is 'Pengadaan'", False, f"Got: {proc_cat.get('label')}")
                else:
                    self.log_test("Has 'procurement' category", False, "Not found in categories")
            else:
                self.log_test("Has 'categories' field", False)
            
            return True
            
        except Exception as e:
            self.log_test("Notification Categories API test", False, f"Error: {str(e)}")
            return False

    def test_rbac_negative(self):
        """Test RBAC: hr@dewiaditya.id should get 403 for procurement APIs"""
        print(f"\n{'='*70}")
        print("TEST 14: RBAC Negative Test (HR role should be denied)")
        print('='*70)
        
        # Login as HR
        if not self.login("hr@dewiaditya.id", "Dewi@123", "HR (should be denied)"):
            self.log_test("RBAC test - HR login", False, "Could not login as HR")
            return False
        
        self.log_test("RBAC test - HR login", True)
        
        # Try to access procurement suppliers (should get 403)
        try:
            response = requests.get(
                f"{BASE_URL}/api/procurement/suppliers",
                headers=self.get_headers("hr@dewiaditya.id"),
                timeout=10
            )
            
            if response.status_code == 403:
                self.log_test("HR role gets 403 for /api/procurement/suppliers", True, "Access correctly denied")
            elif response.status_code == 200:
                self.log_test("HR role gets 403 for /api/procurement/suppliers", False, "HR should NOT have access (got 200)")
            else:
                self.log_test("HR role gets 403 for /api/procurement/suppliers", False, f"Unexpected status: {response.status_code}")
            
            return True
            
        except Exception as e:
            self.log_test("RBAC negative test", False, f"Error: {str(e)}")
            return False

    def test_rbac_positive(self):
        """Test RBAC: finance and gudang should have access"""
        print(f"\n{'='*70}")
        print("TEST 15: RBAC Positive Test (Finance & Gudang should have access)")
        print('='*70)
        
        # Test finance@dewiaditya.id
        if not self.login("finance@dewiaditya.id", "Dewi@123", "Finance (should have access)"):
            self.log_test("RBAC test - Finance login", False, "Could not login as Finance")
        else:
            self.log_test("RBAC test - Finance login", True)
            
            try:
                response = requests.get(
                    f"{BASE_URL}/api/procurement/suppliers",
                    headers=self.get_headers("finance@dewiaditya.id"),
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.log_test("Finance role can access /api/procurement/suppliers", True)
                else:
                    self.log_test("Finance role can access /api/procurement/suppliers", False, f"Got {response.status_code}")
            except Exception as e:
                self.log_test("Finance RBAC test", False, f"Error: {str(e)}")
        
        # Test gudang@dewiaditya.id
        if not self.login("gudang@dewiaditya.id", "Dewi@123", "Gudang (should have access)"):
            self.log_test("RBAC test - Gudang login", False, "Could not login as Gudang")
        else:
            self.log_test("RBAC test - Gudang login", True)
            
            try:
                response = requests.get(
                    f"{BASE_URL}/api/procurement/suppliers",
                    headers=self.get_headers("gudang@dewiaditya.id"),
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.log_test("Gudang role can access /api/procurement/suppliers", True)
                else:
                    self.log_test("Gudang role can access /api/procurement/suppliers", False, f"Got {response.status_code}")
            except Exception as e:
                self.log_test("Gudang RBAC test", False, f"Error: {str(e)}")
        
        return True

    def run_all_tests(self):
        """Run all backend tests"""
        print(f"\n{'='*70}")
        print("PROCUREMENT PORTAL BACKEND API TESTING")
        print("Testing: Phase 2 - Portal Pengadaan end-to-end")
        print('='*70)
        
        # Login as admin first
        if not self.login("admin@garment.com", "Admin@123", "Admin (superadmin)"):
            print("\n❌ Cannot proceed without admin login")
            return False
        
        # Run all API tests
        self.test_procurement_overview()
        self.test_procurement_pipeline()
        self.test_spend_analysis()
        self.test_suppliers_list()
        self.test_suppliers_meta()
        self.test_suppliers_options()
        self.test_supplier_scorecard()
        self.test_migrate_preview()
        self.test_price_lookup()
        self.test_purchase_orders()
        self.test_3way_match()
        self.test_available_for_invoice()
        self.test_notification_categories()
        
        # RBAC tests
        self.test_rbac_negative()
        self.test_rbac_positive()
        
        # Print summary
        print(f"\n{'='*70}")
        print("TEST SUMMARY")
        print('='*70)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        if self.tests_run > 0:
            print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    tester = ProcurementPortalTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
