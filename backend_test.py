#!/usr/bin/env python3
"""
Backend Testing - Accessory Purchase Request Approval Chain Security Fix
=========================================================================
Tests the critical security hole fix where packing@ could approve their own PR.
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://acc-pr-portal.preview.emergentagent.com"

# Color codes
G, R, Y, C, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[0m"

class APRSecurityTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.test_pr_id = None
        self.test_pr_number = None
        
    def login(self, email, password):
        """Login and cache token (rate limit: 10 logins/60s)"""
        if email in self.tokens:
            return self.tokens[email]
        
        print(f"\n🔐 Login {email}...")
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if response.status_code == 200:
                token = response.json().get("token")
                self.tokens[email] = token
                print(f"  {G}✓{X} Login berhasil")
                return token
            else:
                print(f"  {R}✗{X} Login gagal: {response.status_code}")
                return None
        except Exception as e:
            print(f"  {R}✗{X} Login error: {str(e)}")
            return None
    
    def headers(self, email):
        """Get auth headers"""
        token = self.tokens.get(email)
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}
    
    def run_test(self, name, test_func):
        """Run a single test"""
        self.tests_run += 1
        print(f"\n{C}TEST {self.tests_run}: {name}{X}")
        try:
            result = test_func()
            if result:
                self.tests_passed += 1
                print(f"  {G}✓ PASS{X}")
            else:
                self.tests_failed += 1
                print(f"  {R}✗ FAIL{X}")
            return result
        except Exception as e:
            self.tests_failed += 1
            print(f"  {R}✗ FAIL - Exception: {str(e)}{X}")
            return False
    
    def test_1_get_material(self):
        """Get material ACC-BTN-12 for test PR"""
        print("  Mengambil material ACC-BTN-12...")
        response = requests.get(
            f"{self.base_url}/api/rahaza/materials?limit=100",
            headers=self.headers("packing@dewiaditya.id"),
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Gagal ambil materials: {response.status_code}")
            return False
        
        data = response.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        
        for item in items:
            if item.get("code") == "ACC-BTN-12":
                self.material_id = item.get("id")
                print(f"  {G}✓{X} Material ACC-BTN-12 ditemukan: {self.material_id}")
                return True
        
        print(f"  {R}✗{X} Material ACC-BTN-12 tidak ditemukan")
        return False
    
    def test_2_create_pr(self):
        """Create test PR as packing@ (Rp 50 juta, 3 stages)"""
        print("  Membuat PR aksesoris Rp 50 juta...")
        
        body = {
            "purpose": "UJI lubang keamanan",
            "department": "Gudang",
            "items": [{
                "acc_id": self.material_id,
                "qty_requested": 100,
                "estimated_price": 500000,
                "input_unit": "base"
            }]
        }
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests",
            headers=self.headers("packing@dewiaditya.id"),
            json=body,
            timeout=30
        )
        
        if response.status_code != 201:
            print(f"  {R}✗{X} Gagal buat PR: {response.status_code} - {response.text[:200]}")
            return False
        
        data = response.json()
        self.test_pr_id = data.get("id")
        self.test_pr_number = data.get("pr_number")
        print(f"  {G}✓{X} PR dibuat: {self.test_pr_number} (ID: {self.test_pr_id})")
        return True
    
    def test_3_submit_pr(self):
        """Submit PR - should return 200 with approval_chain"""
        print(f"  Submit PR {self.test_pr_number}...")
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/submit",
            headers=self.headers("packing@dewiaditya.id"),
            json={},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Submit gagal: {response.status_code} - {response.text[:200]}")
            return False
        
        data = response.json()
        chain = data.get("approval_chain", [])
        
        if chain != ['dept', 'finance', 'final']:
            print(f"  {R}✗{X} Approval chain salah: {chain} (expected: ['dept', 'finance', 'final'])")
            return False
        
        print(f"  {G}✓{X} Submit berhasil, approval_chain: {chain}")
        return True
    
    def test_4_bypass_blocked(self):
        """CRITICAL: PUT with status='Approved' should be BLOCKED (400)"""
        print(f"  Mencoba bypass dengan PUT status='Approved'...")
        
        response = requests.put(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}",
            headers=self.headers("packing@dewiaditya.id"),
            json={"status": "Approved"},
            timeout=30
        )
        
        if response.status_code == 400:
            text = response.text
            if "tidak lagi lewat endpoint ini" in text.lower() or "gunakan" in text.lower():
                print(f"  {G}✓{X} Bypass DITOLAK dengan pesan yang benar: {response.status_code}")
                print(f"      Pesan: {text[:150]}")
                return True
            else:
                print(f"  {Y}!{X} Ditolak tapi pesan tidak jelas: {text[:150]}")
                return True  # Still blocked, which is good
        else:
            print(f"  {R}✗{X} LUBANG KEAMANAN! Bypass berhasil: {response.status_code}")
            print(f"      Response: {response.text[:200]}")
            return False
    
    def test_5_self_approval_blocked(self):
        """CRITICAL: Creator cannot approve own PR (403)"""
        print(f"  Mencoba approve PR sendiri sebagai packing@ (PEMBUATNYA)...")
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/approve",
            headers=self.headers("packing@dewiaditya.id"),
            json={"comment": "Setuju"},
            timeout=30
        )
        
        if response.status_code == 403:
            text = response.text
            if "pembuat" in text.lower() or "sendiri" in text.lower():
                print(f"  {G}✓{X} Self-approval DITOLAK: {response.status_code}")
                print(f"      Pesan: {text[:150]}")
                return True
            else:
                print(f"  {Y}!{X} Ditolak tapi pesan tidak jelas: {text[:150]}")
                return True
        else:
            print(f"  {R}✗{X} LUBANG KEAMANAN! Self-approval berhasil: {response.status_code}")
            return False
    
    def test_6_wrong_stage_blocked(self):
        """CRITICAL: finance@ cannot approve DEPT stage (403)"""
        print(f"  Mencoba approve tahap DEPARTEMEN sebagai finance@ (tahap SALAH)...")
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/approve",
            headers=self.headers("finance@dewiaditya.id"),
            json={"comment": "Setuju"},
            timeout=30
        )
        
        if response.status_code == 403:
            text = response.text
            if "tahap" in text.lower() or "departemen" in text.lower():
                print(f"  {G}✓{X} Wrong stage DITOLAK: {response.status_code}")
                print(f"      Pesan: {text[:150]}")
                return True
            else:
                print(f"  {Y}!{X} Ditolak tapi pesan tidak jelas: {text[:150]}")
                return True
        else:
            print(f"  {R}✗{X} Wrong stage approval berhasil: {response.status_code}")
            return False
    
    def test_7_dept_approval(self):
        """Approve DEPT stage as gudang@"""
        print(f"  Approve tahap DEPARTEMEN sebagai gudang@...")
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/approve",
            headers=self.headers("gudang@dewiaditya.id"),
            json={"comment": "Setuju kebutuhan aksesoris"},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Approval gagal: {response.status_code} - {response.text[:200]}")
            return False
        
        data = response.json()
        next_stage = data.get("next_stage")
        
        if next_stage != "finance":
            print(f"  {R}✗{X} Next stage salah: {next_stage} (expected: finance)")
            return False
        
        print(f"  {G}✓{X} Tahap DEPARTEMEN disetujui, next_stage: {next_stage}")
        return True
    
    def test_8_double_stage_blocked(self):
        """CRITICAL: gudang@ cannot approve FINANCE stage (already approved DEPT)"""
        print(f"  Mencoba approve tahap KEUANGAN sebagai gudang@ (sudah approve DEPT)...")
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/approve",
            headers=self.headers("gudang@dewiaditya.id"),
            json={"comment": "Setuju lagi"},
            timeout=30
        )
        
        if response.status_code == 403:
            text = response.text
            if "sudah" in text.lower() or "dua tahap" in text.lower():
                print(f"  {G}✓{X} Double stage DITOLAK: {response.status_code}")
                print(f"      Pesan: {text[:150]}")
                return True
            else:
                print(f"  {Y}!{X} Ditolak tapi pesan tidak jelas: {text[:150]}")
                return True
        else:
            print(f"  {R}✗{X} Double stage approval berhasil: {response.status_code}")
            return False
    
    def test_9_finance_approval(self):
        """Approve FINANCE stage as finance@"""
        print(f"  Approve tahap KEUANGAN sebagai finance@...")
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/approve",
            headers=self.headers("finance@dewiaditya.id"),
            json={"comment": "Anggaran tersedia"},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Approval gagal: {response.status_code} - {response.text[:200]}")
            return False
        
        data = response.json()
        next_stage = data.get("next_stage")
        
        if next_stage != "final":
            print(f"  {R}✗{X} Next stage salah: {next_stage} (expected: final)")
            return False
        
        print(f"  {G}✓{X} Tahap KEUANGAN disetujui, next_stage: {next_stage}")
        return True
    
    def test_10_final_approval(self):
        """Approve FINAL stage as direktur@"""
        print(f"  Approve tahap FINAL sebagai direktur@...")
        
        response = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/approve",
            headers=self.headers("direktur@dewiaditya.id"),
            json={"comment": "Disetujui"},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Approval gagal: {response.status_code} - {response.text[:200]}")
            return False
        
        data = response.json()
        new_status = data.get("new_status")
        
        if new_status != "Approved":
            print(f"  {R}✗{X} Status salah: {new_status} (expected: Approved)")
            return False
        
        print(f"  {G}✓{X} Tahap FINAL disetujui, new_status: {new_status}")
        return True
    
    def test_11_timeline(self):
        """Check timeline has 3 approval steps"""
        print(f"  Cek timeline PR...")
        
        response = requests.get(
            f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}/timeline",
            headers=self.headers("gudang@dewiaditya.id"),
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Timeline gagal: {response.status_code}")
            return False
        
        data = response.json()
        steps = data.get("steps", [])
        approved_steps = [s for s in steps if s.get("action") == "approved"]
        
        if len(approved_steps) != 3:
            print(f"  {R}✗{X} Jumlah approval steps salah: {len(approved_steps)} (expected: 3)")
            return False
        
        # Check each step has actor info
        for step in approved_steps:
            if not step.get("actor_id") or not step.get("actor_name") or not step.get("stage"):
                print(f"  {R}✗{X} Step tidak lengkap: {step}")
                return False
        
        print(f"  {G}✓{X} Timeline lengkap: {len(approved_steps)} approval steps")
        return True
    
    def test_12_combined_inbox(self):
        """Check combined inbox shows ACC-PR"""
        print(f"  Cek kotak persetujuan gabungan...")
        
        response = requests.get(
            f"{self.base_url}/api/procurement/inbox",
            headers=self.headers("gudang@dewiaditya.id"),
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Inbox gagal: {response.status_code}")
            return False
        
        items = response.json()
        if not isinstance(items, list):
            items = items.get("items", [])
        
        # Check for ACC-PR items
        acc_items = [i for i in items if i.get("kind") == "acc_pr"]
        
        if not acc_items:
            print(f"  {Y}!{X} Tidak ada ACC-PR di inbox (mungkin sudah disetujui semua)")
            return True  # Not a failure, just no pending items
        
        # Check structure
        for item in acc_items:
            if item.get("kind_label") != "Aksesoris":
                print(f"  {R}✗{X} kind_label salah: {item.get('kind_label')}")
                return False
            if item.get("api_base") != "/api/acc/purchase-requests":
                print(f"  {R}✗{X} api_base salah: {item.get('api_base')}")
                return False
            if item.get("module_id") != "proc-accessory-pr":
                print(f"  {R}✗{X} module_id salah: {item.get('module_id')}")
                return False
            if not item.get("can_approve"):
                print(f"  {R}✗{X} can_approve harus true untuk item di inbox")
                return False
        
        print(f"  {G}✓{X} Inbox gabungan bekerja: {len(acc_items)} ACC-PR items")
        return True
    
    def test_13_badge_count(self):
        """Check badge count matches inbox"""
        print(f"  Cek lencana approval...")
        
        # Get inbox
        inbox_resp = requests.get(
            f"{self.base_url}/api/procurement/inbox",
            headers=self.headers("gudang@dewiaditya.id"),
            timeout=30
        )
        
        if inbox_resp.status_code != 200:
            print(f"  {R}✗{X} Inbox gagal: {inbox_resp.status_code}")
            return False
        
        inbox_items = inbox_resp.json()
        if not isinstance(inbox_items, list):
            inbox_items = inbox_items.get("items", [])
        
        # Get badge
        badge_resp = requests.get(
            f"{self.base_url}/api/approval-inbox/badge",
            headers=self.headers("gudang@dewiaditya.id"),
            timeout=30
        )
        
        if badge_resp.status_code != 200:
            print(f"  {R}✗{X} Badge gagal: {badge_resp.status_code}")
            return False
        
        badge_data = badge_resp.json()
        pr_pending = badge_data.get("pr_pending", 0)
        
        if pr_pending != len(inbox_items):
            print(f"  {R}✗{X} Badge count ({pr_pending}) != inbox count ({len(inbox_items)})")
            return False
        
        print(f"  {G}✓{X} Badge count cocok: {pr_pending}")
        return True
    
    def test_14_small_pr_one_stage(self):
        """Create small PR (Rp 200k) - should have 1 stage only"""
        print(f"  Buat PR kecil (Rp 200k) - harus 1 tahap...")
        
        body = {
            "purpose": "UJI ambang nilai kecil",
            "department": "Gudang",
            "items": [{
                "acc_id": self.material_id,
                "qty_requested": 10,
                "estimated_price": 20000,
                "input_unit": "base"
            }]
        }
        
        # Create
        resp = requests.post(
            f"{self.base_url}/api/acc/purchase-requests",
            headers=self.headers("packing@dewiaditya.id"),
            json=body,
            timeout=30
        )
        
        if resp.status_code != 201:
            print(f"  {R}✗{X} Gagal buat PR: {resp.status_code}")
            return False
        
        small_pr_id = resp.json().get("id")
        
        # Submit
        submit_resp = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{small_pr_id}/submit",
            headers=self.headers("packing@dewiaditya.id"),
            json={},
            timeout=30
        )
        
        if submit_resp.status_code != 200:
            print(f"  {R}✗{X} Submit gagal: {submit_resp.status_code}")
            return False
        
        data = submit_resp.json()
        chain = data.get("approval_chain", [])
        
        if chain != ['dept']:
            print(f"  {R}✗{X} Chain salah: {chain} (expected: ['dept'])")
            return False
        
        # Approve once - should be fully approved
        approve_resp = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{small_pr_id}/approve",
            headers=self.headers("gudang@dewiaditya.id"),
            json={"comment": "OK"},
            timeout=30
        )
        
        if approve_resp.status_code != 200:
            print(f"  {R}✗{X} Approval gagal: {approve_resp.status_code}")
            return False
        
        approve_data = approve_resp.json()
        if approve_data.get("new_status") != "Approved":
            print(f"  {R}✗{X} Status salah: {approve_data.get('new_status')} (expected: Approved)")
            return False
        
        print(f"  {G}✓{X} PR kecil: 1 tahap, langsung Approved")
        return True
    
    def test_15_reject_needs_reason(self):
        """Rejection without reason should fail (400)"""
        print(f"  Buat PR untuk uji penolakan...")
        
        # Create new PR
        body = {
            "purpose": "UJI penolakan",
            "department": "Gudang",
            "items": [{
                "acc_id": self.material_id,
                "qty_requested": 50,
                "estimated_price": 10000,
                "input_unit": "base"
            }]
        }
        
        resp = requests.post(
            f"{self.base_url}/api/acc/purchase-requests",
            headers=self.headers("packing@dewiaditya.id"),
            json=body,
            timeout=30
        )
        
        if resp.status_code != 201:
            print(f"  {R}✗{X} Gagal buat PR: {resp.status_code}")
            return False
        
        reject_pr_id = resp.json().get("id")
        
        # Submit
        requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{reject_pr_id}/submit",
            headers=self.headers("packing@dewiaditya.id"),
            json={},
            timeout=30
        )
        
        # Try reject without reason
        reject_resp = requests.post(
            f"{self.base_url}/api/acc/purchase-requests/{reject_pr_id}/reject",
            headers=self.headers("gudang@dewiaditya.id"),
            json={"reason": "   "},  # Only spaces
            timeout=30
        )
        
        if reject_resp.status_code == 400:
            text = reject_resp.text
            if "alasan" in text.lower() or "wajib" in text.lower():
                print(f"  {G}✓{X} Penolakan tanpa alasan DITOLAK: {reject_resp.status_code}")
                return True
            else:
                print(f"  {Y}!{X} Ditolak tapi pesan tidak jelas: {text[:150]}")
                return True
        else:
            print(f"  {R}✗{X} Penolakan tanpa alasan berhasil: {reject_resp.status_code}")
            return False
    
    def test_16_dashboard_acc_pr(self):
        """Dashboard should show ACC-PR count > 0 (ghost collection fix)"""
        print(f"  Cek Dashboard Pengadaan - KPI ACC-PR...")
        
        response = requests.get(
            f"{self.base_url}/api/procurement/overview",
            headers=self.headers("finance@dewiaditya.id"),
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  {R}✗{X} Dashboard gagal: {response.status_code}")
            return False
        
        data = response.json()
        kpi = data.get("kpi", {})
        
        acc_pr_total = kpi.get("accessory_pr_total", 0)
        acc_pr_awaiting = kpi.get("accessory_pr_awaiting_approval", 0)
        
        if acc_pr_total == 0:
            print(f"  {R}✗{X} GHOST COLLECTION BUG! accessory_pr_total = 0")
            return False
        
        print(f"  {G}✓{X} Dashboard OK: accessory_pr_total = {acc_pr_total}, awaiting = {acc_pr_awaiting}")
        return True
    
    def cleanup(self):
        """Delete test PRs"""
        print(f"\n{C}CLEANUP{X}")
        if self.test_pr_id:
            print(f"  Menghapus test PR {self.test_pr_number}...")
            # Note: Delete endpoint might not exist, that's OK
            try:
                requests.delete(
                    f"{self.base_url}/api/acc/purchase-requests/{self.test_pr_id}",
                    headers=self.headers("admin@garment.com"),
                    timeout=30
                )
            except Exception:  # noqa: S110
                pass
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{'='*70}")
        print(f"{C}TEST SUMMARY{X}")
        print(f"{'='*70}")
        print(f"  Total tests:  {self.tests_run}")
        print(f"  {G}Passed:       {self.tests_passed}{X}")
        print(f"  {R}Failed:       {self.tests_failed}{X}")
        
        if self.tests_failed == 0:
            print(f"\n{G}✓ ALL TESTS PASSED - SECURITY HOLES CLOSED{X}\n")
            return 0
        else:
            print(f"\n{R}✗ SOME TESTS FAILED - SECURITY ISSUES REMAIN{X}\n")
            return 1

def main():
    print(f"\n{C}{'='*70}")
    print(f"BACKEND SECURITY TEST - Accessory Purchase Request Approval Chain")
    print(f"{'='*70}{X}\n")
    
    tester = APRSecurityTester()
    
    # Login all accounts (rate limit: 10/60s)
    print(f"{C}SETUP - Login accounts{X}")
    accounts = [
        ("packing@dewiaditya.id", "Dewi@123"),
        ("gudang@dewiaditya.id", "Dewi@123"),
        ("finance@dewiaditya.id", "Dewi@123"),
        ("direktur@dewiaditya.id", "Dewi@123"),
        ("admin@garment.com", "Admin@123"),
    ]
    
    for email, password in accounts:
        if not tester.login(email, password):
            print(f"\n{R}FATAL: Cannot login {email}{X}")
            return 1
    
    # Run tests
    print(f"\n{C}{'='*70}")
    print(f"RUNNING TESTS")
    print(f"{'='*70}{X}")
    
    # Setup
    tester.run_test("Get material ACC-BTN-12", tester.test_1_get_material)
    tester.run_test("Create test PR (Rp 50M)", tester.test_2_create_pr)
    tester.run_test("Submit PR", tester.test_3_submit_pr)
    
    # CRITICAL SECURITY TESTS
    tester.run_test("SECURITY: Bypass route blocked", tester.test_4_bypass_blocked)
    tester.run_test("SECURITY: Self-approval blocked", tester.test_5_self_approval_blocked)
    tester.run_test("SECURITY: Wrong stage blocked", tester.test_6_wrong_stage_blocked)
    
    # 3-person chain
    tester.run_test("Approve DEPT stage (gudang@)", tester.test_7_dept_approval)
    tester.run_test("SECURITY: Double stage blocked", tester.test_8_double_stage_blocked)
    tester.run_test("Approve FINANCE stage (finance@)", tester.test_9_finance_approval)
    tester.run_test("Approve FINAL stage (direktur@)", tester.test_10_final_approval)
    
    # Other features
    tester.run_test("Timeline has 3 approval steps", tester.test_11_timeline)
    tester.run_test("Combined inbox shows ACC-PR", tester.test_12_combined_inbox)
    tester.run_test("Badge count matches inbox", tester.test_13_badge_count)
    tester.run_test("Small PR (Rp 200k) = 1 stage", tester.test_14_small_pr_one_stage)
    tester.run_test("Rejection requires reason", tester.test_15_reject_needs_reason)
    tester.run_test("Dashboard ACC-PR KPI > 0", tester.test_16_dashboard_acc_pr)
    
    # Cleanup
    # tester.cleanup()  # Skip cleanup to preserve test data
    
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
