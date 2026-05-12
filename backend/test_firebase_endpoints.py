"""
FasalX -- Firebase Authentication & API Endpoint Test Runner
============================================================
Tests all protected endpoints using a real Firebase user.
Run:  python test_firebase_endpoints.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import json
import time

# ─── Configuration ───────────────────────────────────────────────────────────
FIREBASE_WEB_API_KEY = "AIzaSyBz59RbdIO7z5AYOzGz6u2X5DSHs2tzO-0"
TEST_EMAIL = "testfarmer@fasalx.dev"
TEST_PASSWORD = "TestFarmer@123"
BASE_URL = "http://localhost:8000/api/v1"

# ─── Colors ──────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"

def banner(text):
    print(f"\n{'='*70}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{'='*70}")

def step(num, title):
    print(f"\n{BOLD}{YELLOW}-- Step {num}: {title} --{RESET}")

def ok(msg):
    print(f"  {GREEN}[PASS] {msg}{RESET}")

def fail(msg):
    print(f"  {RED}[FAIL] {msg}{RESET}")

def info(msg):
    print(f"  {DIM}{msg}{RESET}")

def print_json(data, indent=4):
    """Pretty print JSON response"""
    formatted = json.dumps(data, indent=indent, default=str)
    for line in formatted.split("\n"):
        print(f"    {CYAN}{line}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 0: Ensure test user exists via Firebase Admin SDK
# ═══════════════════════════════════════════════════════════════════════════════
def ensure_test_user():
    step(0, "Ensure Test User Exists in Firebase")
    try:
        import firebase_admin
        from firebase_admin import credentials, auth as fb_auth

        # Initialize Firebase Admin if not already
        try:
            app = firebase_admin.get_app()
        except ValueError:
            cred = credentials.Certificate("./serviceAccountKey.json")
            app = firebase_admin.initialize_app(cred)

        try:
            user = fb_auth.get_user_by_email(TEST_EMAIL)
            ok(f"User already exists: {user.uid}")
        except fb_auth.UserNotFoundError:
            user = fb_auth.create_user(
                email=TEST_EMAIL,
                password=TEST_PASSWORD,
                display_name="Test Farmer"
            )
            ok(f"Created new user: {user.uid}")
        return user.uid
    except Exception as e:
        fail(f"Firebase Admin error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 1: Sign in and get ID Token
# ═══════════════════════════════════════════════════════════════════════════════
def get_id_token():
    step(1, "Sign In → Get Firebase ID Token")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "returnSecureToken": True
    }

    info(f"POST {url[:60]}...")
    r = requests.post(url, json=payload)

    if r.status_code == 200:
        data = r.json()
        token = data["idToken"]
        ok(f"Signed in as: {data.get('email')}")
        ok(f"UID: {data.get('localId')}")
        ok(f"Token expires in: {data.get('expiresIn')}s")
        info(f"Token preview: {token[:50]}...{token[-20:]}")
        return token
    else:
        fail(f"Sign-in failed ({r.status_code})")
        print_json(r.json())
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 2: POST /users/sync
# ═══════════════════════════════════════════════════════════════════════════════
def test_sync_user(headers):
    step(2, "POST /users/sync — Sync Firebase User → MongoDB")

    url = f"{BASE_URL}/users/sync"
    info(f"POST {url}")
    r = requests.post(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        ok("User synchronized to MongoDB")
        print_json(r.json())
    else:
        fail(f"Sync failed")
        print(f"Response text: {r.text}")
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 3: GET /users/me
# ═══════════════════════════════════════════════════════════════════════════════
def test_get_profile(headers):
    step(3, "GET /users/me — Fetch Profile")

    url = f"{BASE_URL}/users/me"
    info(f"GET {url}")
    r = requests.get(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        ok("Profile retrieved")
        print_json(r.json())
    else:
        fail("Failed to get profile")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 4: POST /users/me — Update Profile
# ═══════════════════════════════════════════════════════════════════════════════
def test_update_profile(headers):
    step(4, "POST /users/me — Update Profile (FarmerProfile)")

    url = f"{BASE_URL}/users/me"
    payload = {
        "display_name": "Ravi Kumar",
        "preferred_language": "hi",
        "farm_size_acres": 5.5,
        "phone_number": "+919876543210",
        "location": {
            "latitude": 20.5937,
            "longitude": 78.9629
        }
    }

    info(f"POST {url}")
    info(f"Payload: {json.dumps(payload, indent=2)[:100]}...")
    r = requests.post(url, headers=headers, json=payload)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        ok("Profile updated")
        print_json(r.json())
    else:
        fail("Failed to update profile")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 5: GET /users/me — Verify Updated Profile
# ═══════════════════════════════════════════════════════════════════════════════
def test_verify_updated_profile(headers):
    step(5, "GET /users/me — Verify Profile Was Updated")

    url = f"{BASE_URL}/users/me"
    info(f"GET {url}")
    r = requests.get(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        data = r.json()
        if data.get("display_name") == "Ravi Kumar":
            ok(f"display_name = '{data['display_name']}'")
        if data.get("preferred_language") == "hi":
            ok(f"preferred_language = '{data['preferred_language']}'")
        if data.get("farm_size_acres") == 5.5:
            ok(f"farm_size_acres = {data['farm_size_acres']}")
        print_json(data)
    else:
        fail("Failed to verify profile")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 6: GET /users/activities
# ═══════════════════════════════════════════════════════════════════════════════
def test_get_activities(headers):
    step(6, "GET /users/activities — Activity History")

    url = f"{BASE_URL}/users/activities?limit=10&offset=0"
    info(f"GET {url}")
    r = requests.get(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        data = r.json()
        activities = data.get("activities", [])
        ok(f"Found {len(activities)} activities")
        print_json(data)
    else:
        fail("Failed to get activities")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 7: GET /agronomy/mandi-prices
# ═══════════════════════════════════════════════════════════════════════════════
def test_mandi_prices(headers):
    step(7, "GET /agronomy/mandi-prices — Market Prices")

    url = f"{BASE_URL}/agronomy/mandi-prices?commodity=Wheat&state=Madhya Pradesh"
    info(f"GET {url}")
    r = requests.get(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        data = r.json()
        ok("Mandi prices retrieved")
        # Truncate if too much data
        truncated = json.dumps(data, indent=2, default=str)
        if len(truncated) > 800:
            print(f"    {CYAN}{truncated[:800]}...{RESET}")
            info(f"(response truncated, total {len(truncated)} chars)")
        else:
            print_json(data)
    else:
        fail(f"Mandi prices failed")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 8: GET /agronomy/weather
# ═══════════════════════════════════════════════════════════════════════════════
def test_weather(headers):
    step(8, "GET /agronomy/weather — Weather Data")

    url = f"{BASE_URL}/agronomy/weather?lat=20.5937&lon=78.9629"
    info(f"GET {url}")
    r = requests.get(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        data = r.json()
        ok("Weather data retrieved")
        truncated = json.dumps(data, indent=2, default=str)
        if len(truncated) > 800:
            print(f"    {CYAN}{truncated[:800]}...{RESET}")
            info(f"(response truncated, total {len(truncated)} chars)")
        else:
            print_json(data)
    else:
        fail(f"Weather fetch failed")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 9: POST /users/logout — Revoke Tokens
# ═══════════════════════════════════════════════════════════════════════════════
def test_logout(headers):
    step(9, "POST /users/logout — Revoke All Tokens")

    # Small delay so Firebase processes the revocation
    time.sleep(1)
    url = f"{BASE_URL}/users/logout"
    info(f"POST {url}")
    r = requests.post(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        ok("Tokens revoked — all sessions invalidated")
        print_json(r.json())
    else:
        fail("Logout failed")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 10: Verify token is revoked
# ═══════════════════════════════════════════════════════════════════════════════
def test_revoked_token(headers):
    step(10, "GET /users/me — Verify Token Is Revoked (expect 401)")

    url = f"{BASE_URL}/users/me"
    info(f"GET {url} (using OLD revoked token)")
    r = requests.get(url, headers=headers)

    print(f"  Status: {YELLOW}{r.status_code}{RESET}")
    if r.status_code == 401:
        ok("Correctly rejected revoked token!")
        print_json(r.json())
    else:
        fail(f"Expected 401, got {r.status_code}")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 11: Re-authenticate after logout
# ═══════════════════════════════════════════════════════════════════════════════
def test_re_auth():
    step(11, "Re-Authenticate After Logout — Get Fresh Token")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "returnSecureToken": True
    }

    info(f"POST Firebase signIn...")
    r = requests.post(url, json=payload)

    if r.status_code == 200:
        data = r.json()
        token = data["idToken"]
        ok(f"Re-authenticated successfully")
        ok(f"New token preview: {token[:40]}...")
        return token
    else:
        fail("Re-authentication failed")
        print_json(r.json())
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 12: POST /users/deactivate
# ═══════════════════════════════════════════════════════════════════════════════
def test_deactivate(headers):
    step(12, "POST /users/deactivate — Soft Delete Account")

    url = f"{BASE_URL}/users/deactivate"
    info(f"POST {url}")
    r = requests.post(url, headers=headers)

    print(f"  Status: {GREEN if r.status_code == 200 else RED}{r.status_code}{RESET}")
    if r.status_code == 200:
        ok("Account deactivated (soft delete)")
        print_json(r.json())
    else:
        fail("Deactivation failed")
        print_json(r.json())
    return r.status_code


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN — Run all tests
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    banner("FasalX — Firebase Auth & API Endpoint Test Suite")
    print(f"  Target: {BASE_URL}")
    print(f"  User:   {TEST_EMAIL}")
    print(f"  Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Step 0: Ensure user exists
    uid = ensure_test_user()
    if not uid:
        print(f"\n{RED}ABORT: Cannot create/find Firebase user{RESET}")
        sys.exit(1)

    # Step 1: Get ID token
    token = get_id_token()
    if not token:
        print(f"\n{RED}ABORT: Cannot get ID token{RESET}")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Step 2-8: Core endpoint tests
    results["sync"]       = test_sync_user(headers)
    results["get_profile"] = test_get_profile(headers)
    results["update_profile"] = test_update_profile(headers)
    results["verify_update"]  = test_verify_updated_profile(headers)
    results["activities"]     = test_get_activities(headers)
    results["mandi_prices"]   = test_mandi_prices(headers)
    results["weather"]        = test_weather(headers)

    # Step 9: Logout (revokes token)
    results["logout"] = test_logout(headers)

    # Step 10: Verify revoked token is rejected
    results["revoked_check"] = test_revoked_token(headers)

    # Step 11: Re-authenticate
    new_token = test_re_auth()
    if new_token:
        new_headers = {
            "Authorization": f"Bearer {new_token}",
            "Content-Type": "application/json"
        }

        # Step 12: Deactivate (soft delete) — re-auth needed since previous token was revoked
        results["deactivate"] = test_deactivate(new_headers)
    else:
        results["deactivate"] = "SKIPPED"

    # ─── Summary ─────────────────────────────────────────────────────────
    banner("TEST RESULTS SUMMARY")

    passed = 0
    failed = 0
    for name, code in results.items():
        if name == "revoked_check":
            # 401 is the expected result here
            expected = 401
        else:
            expected = 200

        if code == expected:
            print(f"  {GREEN}✓ PASS{RESET}  {name:<20} → {code}")
            passed += 1
        elif code == "SKIPPED":
            print(f"  {YELLOW}○ SKIP{RESET}  {name:<20}")
        else:
            print(f"  {RED}✗ FAIL{RESET}  {name:<20} → {code} (expected {expected})")
            failed += 1

    print(f"\n  {BOLD}Total: {passed} passed, {failed} failed, out of {len(results)} tests{RESET}")

    if failed == 0:
        print(f"\n  {GREEN}{BOLD}ALL TESTS PASSED!{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}Some tests failed. Check output above.{RESET}\n")


if __name__ == "__main__":
    main()
