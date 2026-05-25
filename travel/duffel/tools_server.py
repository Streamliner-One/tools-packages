#!/usr/bin/env python3
"""
Tools Server Credential Helper
Fetches credentials from tools-config-server using curl (cookie-jar auth).
This is the reliable pattern - Python requests.Session() has cookie issues.
"""

import subprocess
import json
import sys
import tempfile
import os

TOOLS_SERVER_URL = os.environ.get("TOOLS_SERVER_URL", "http://localhost:8080")
TOOLS_SERVER_PASSWORD = os.environ.get("TOOLS_SERVER_PASSWORD")

if not TOOLS_SERVER_PASSWORD:
    raise RuntimeError("Set TOOLS_SERVER_PASSWORD for your local tools-server instance")


def get_credential(credential_id: str) -> dict:
    """
    Fetch a credential from Tools Server using curl.
    
    Args:
        credential_id: The credential ID (e.g., "duffel", "duffel-1775151120476")
    
    Returns:
        Credential object with fields
    
    Raises:
        RuntimeError: If credential fetch fails
    """
    # Create temp cookie file
    cookie_file = tempfile.mktemp()
    
    try:
        # Step 1: Login (store cookies)
        login_cmd = [
            "curl", "-s", "-c", cookie_file,
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"password": TOOLS_SERVER_PASSWORD}),
            f"{TOOLS_SERVER_URL}/api/login"
        ]
        
        login_result = subprocess.run(login_cmd, capture_output=True, text=True, timeout=10)
        if login_result.returncode != 0:
            raise RuntimeError(f"Login failed: {login_result.stderr}")
        
        login_data = json.loads(login_result.stdout)
        if not login_data.get("success"):
            raise RuntimeError(f"Login failed: {login_result.stdout}")
        
        # Step 2: Fetch credential (use cookies)
        cred_cmd = [
            "curl", "-s", "-b", cookie_file,
            f"{TOOLS_SERVER_URL}/api/credentials/{credential_id}"
        ]
        
        cred_result = subprocess.run(cred_cmd, capture_output=True, text=True, timeout=10)
        if cred_result.returncode != 0:
            raise RuntimeError(f"Fetch failed: {cred_result.stderr}")
        
        # Check for auth error
        if cred_result.stdout.startswith('{"error"'):
            raise RuntimeError(f"Unauthorized (401) - check tools server")
        
        cred_data = json.loads(cred_result.stdout)
        return cred_data
        
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON response: {e}")
    finally:
        # Cleanup
        if os.path.exists(cookie_file):
            os.remove(cookie_file)


def get_api_key(credential_id: str) -> str:
    """
    Extract API key from credential.
    
    Args:
        credential_id: The credential ID
    
    Returns:
        API key string
    """
    cred = get_credential(credential_id)
    
    # Try different field locations
    api_key = (
        cred.get("fields", {}).get("apiKey", {}).get("value") or
        cred.get("primaryKey") or
        cred.get("apiToken")
    )
    
    if not api_key:
        raise RuntimeError(f"No API key found in credential '{credential_id}'")
    
    return api_key


if __name__ == "__main__":
    # CLI usage: python tools_server.py get_credential <credential_id>
    if len(sys.argv) < 3:
        print("Usage: python tools_server.py get_credential <credential_id>")
        print("       python tools_server.py get_api_key <credential_id>")
        sys.exit(1)
    
    action = sys.argv[1]
    cred_id = sys.argv[2]
    
    try:
        if action == "get_credential":
            cred = get_credential(cred_id)
            print(json.dumps(cred, indent=2))
        elif action == "get_api_key":
            key = get_api_key(cred_id)
            print(key)
        else:
            print(f"Unknown action: {action}")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
