#!/usr/bin/env python
"""Debug Zerodha authentication."""

import os
from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()

api_key = os.getenv("ZERODHA_API_KEY")
access_token = os.getenv("ZERODHA_ACCESS_TOKEN")
api_secret = os.getenv("ZERODHA_API_SECRET")

print("🔍 Zerodha Authentication Debug\n")
print(f"API Key: {api_key[:10]}..." if api_key else "❌ Missing API_KEY")
print(f"API Secret: {api_secret[:10]}..." if api_secret else "❌ Missing API_SECRET")
print(f"Access Token: {access_token[:10]}..." if access_token else "❌ Missing ACCESS_TOKEN")
print()

if not (api_key and access_token):
    print("❌ Missing credentials")
    exit(1)

print("Testing KiteConnect connection...\n")
try:
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    print("⏳ Fetching holdings...")
    holdings = kite.holdings()
    print(f"✅ Success! Found {len(holdings)} holdings")

    if holdings:
        for h in holdings[:3]:  # Show first 3
            print(f"   - {h['tradingsymbol']}: {h['quantity']} @ ₹{h['last_price']}")

except Exception as e:
    print(f"❌ Error: {e}")
    print("\nPossible solutions:")
    print("1. Access token may have expired (they expire daily)")
    print("2. API Key and API Secret may not match")
    print("3. Zerodha API may be down")
    print("4. Session may have timed out")
    print("\nTry regenerating the token:")
    print("  python tests/zerodha_token_generator.py")
