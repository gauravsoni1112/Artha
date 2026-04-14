#!/usr/bin/env python
"""
Manual Zerodha token generation using requests library.
This bypasses KiteConnect and uses the raw API.
"""

import os
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ZERODHA_API_KEY")
API_SECRET = os.getenv("ZERODHA_API_SECRET")

print("🔐 Zerodha Manual Token Generator\n")
print(f"API Key: {API_KEY}")
print(f"API Secret: {API_SECRET}\n")

request_token = input("🔑 Enter the request_token: ").strip()

if not request_token:
    print("❌ No request_token provided")
    exit(1)

print(f"\n⏳ Generating access_token...\n")

# Calculate checksum: SHA256(api_key + request_token + api_secret)
checksum_input = API_KEY + request_token + API_SECRET
checksum = hashlib.sha256(checksum_input.encode()).hexdigest()

print(f"Checksum input: {checksum_input}")
print(f"Checksum: {checksum}\n")

# Make the API call
url = "https://api.kite.trade/session/token"
payload = {
    "api_key": API_KEY,
    "request_token": request_token,
    "checksum": checksum
}

print(f"POST {url}")
print(f"Data: {payload}\n")

try:
    response = requests.post(url, data=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}\n")

    if response.status_code == 200:
        data = response.json()
        if "data" in data and "access_token" in data["data"]:
            access_token = data["data"]["access_token"]
            print(f"✅ Success!\n")
            print(f"New Access Token: {access_token}\n")
            print("📝 Update your .env file:")
            print(f"   ZERODHA_ACCESS_TOKEN={access_token}\n")
        else:
            print(f"❌ No access_token in response: {data}")
    else:
        print(f"❌ API Error: {response.text}")

except Exception as e:
    print(f"❌ Error: {e}")
