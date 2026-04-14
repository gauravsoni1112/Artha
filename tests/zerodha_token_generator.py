#!/usr/bin/env python
"""
Zerodha Access Token Generator.

Zerodha access tokens expire daily. Use this script to generate a fresh token.

Steps:
  1. Run this script: python tests/zerodha_token_generator.py
  2. A browser window will open to Kite login
  3. Login with your Zerodha credentials
  4. You'll be redirected with a request_token in the URL
  5. Copy the request_token and paste it here
  6. Script will generate your access_token
  7. Update .env with the new token
"""

import os
import webbrowser
import hashlib
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load .env file
load_dotenv()

# Get credentials from environment
API_KEY = os.getenv("ZERODHA_API_KEY")
API_SECRET = os.getenv("ZERODHA_API_SECRET")

if not API_KEY:
    print("❌ Error: ZERODHA_API_KEY not found in .env")
    exit(1)

if not API_SECRET:
    print("❌ Error: ZERODHA_API_SECRET not found in .env")
    exit(1)

print(f"✅ Using API Key: {API_KEY[:10]}...")
print(f"✅ Using API Secret: {API_SECRET[:10]}...")
print("\n🔐 Zerodha Access Token Generator\n")

# Initialize KiteConnect
kite = KiteConnect(api_key=API_KEY)

# Generate login URL
login_url = kite.login_url()
print(f"📖 Login URL: {login_url}")
print("\n📱 Opening browser for login...\n")

# Try to open browser
try:
    webbrowser.open(login_url)
except Exception as e:
    print(f"⚠️  Could not open browser automatically: {e}")
    print(f"   Please manually visit: {login_url}")

print("After login, you'll be redirected to a URL like:")
print("  http://127.0.0.1/?action=login&type=login&status=success&request_token=XXXXX")
print("")

# Get request_token from user
request_token = input("🔑 Enter the request_token from the redirect URL: ").strip()

if not request_token:
    print("❌ No request_token provided")
    exit(1)

print(f"\n⏳ Generating access_token...")

try:
    # The checksum needs to be: SHA256(api_key + request_token + api_secret)
    checksum = hashlib.sha256((API_KEY + request_token + API_SECRET).encode()).hexdigest()

    # Call generate_session with proper parameters
    data = kite.generate_session(
        request_token=request_token,
        api_secret=checksum  # Pass the checksum as api_secret parameter
    )

    access_token = data.get("access_token")

    if not access_token:
        print(f"❌ No access_token in response: {data}")
        exit(1)

    print(f"✅ Success!\n")
    print(f"New Access Token: {access_token}\n")
    print("📝 Update your .env file:")
    print(f"   ZERODHA_ACCESS_TOKEN={access_token}\n")
    print("🔄 Then test the connection:")
    print("   python tests/zerodha_debug.py")

except Exception as e:
    print(f"❌ Error generating token: {e}")
    print("\n🔧 Troubleshooting:")
    print("1. Make sure request_token is correct (copy from redirect URL)")
    print("2. Verify API_KEY and API_SECRET are from the SAME app")
    print("3. Request tokens expire quickly - try again if it's been > 5 minutes")
    print(f"4. Full error: {str(e)}")
    exit(1)
