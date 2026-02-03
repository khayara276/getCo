import requests
import json
import time
import os
import threading
import base64
import random
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 🔒 ENCRYPTED CONFIGURATION
# ==========================================
# Gist Config (Data persistence ke liye)
_GID = os.getenv("GIST_ID")
_GTK = os.getenv("GH_TOKEN")

# Files Mapping in Gist
_F1 = "sys_log_primary.txt"  # For Normal Data
_F2 = "sys_log_kernel.txt"   # For Special Data (SVI/SVG)

# Base64 Encoded Endpoints (Apke wale URLs)
_EPS = [
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP3R5cGU9bG9nJmluZGV4TmFtZT1pbnRlcmVzdF9jZW50ZXJzJmxvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP2luZGV4TmFtZT1pbnRlcmVzdF9jZW50ZXJzJmxvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP2xvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP3dlYklEPTI1NjQ3"
]

# Runtime Config
_LIM = 21000 # 5h 50m Auto Stop
_INT = 7     # Polling Interval

# Decoder
_d = lambda b: base64.b64decode(b).decode('utf-8')

class DataNode:
    def __init__(self):
        self.seen = set()
        self.session = requests.Session()
        # Fake Headers for stealth
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        })
        self.start_ts = time.time()
        self.active = True
        
        # Load previous data from Gist
        self._load_cache()

    def _load_cache(self):
        """Fetch existing data from Gist to avoid duplicates"""
        print("System: Syncing Cache...")
        if not _GID or not _GTK:
            print("⚠️ System: Gist Config Missing. Running in local mode.")
            return

        try:
            h = {"Authorization": f"token {_GTK}"}
            r = requests.get(f"https://api.github.com/gists/{_GID}", headers=h)
            if r.status_code == 200:
                files = r.json().get('files', {})
                # Load F1
                if _F1 in files:
                    c1 = files[_F1]['content'].split('\n')
                    self.seen.update([x.strip() for x in c1 if x.strip()])
                # Load F2
                if _F2 in files:
                    c2 = files[_F2]['content'].split('\n')
                    self.seen.update([x.strip() for x in c2 if x.strip()])
                
                print(f"System: Cache Loaded ({len(self.seen)} nodes).")
            else:
                print(f"System: Cache Sync Failed ({r.status_code})")
        except Exception as e:
            print(f"System: Cache Error: {e}")

    def _push_update(self, raw_data, is_special):
        """Push new data to Gist immediately"""
        if not _GID or not _GTK: return
        
        target_file = _F2 if is_special else _F1
        
        try:
            # First get current content to append
            h = {"Authorization": f"token {_GTK}"}
            r = requests.get(f"https://api.github.com/gists/{_GID}", headers=h)
            current_content = ""
            if r.status_code == 200:
                files = r.json().get('files', {})
                if target_file in files:
                    current_content = files[target_file]['content']
            
            # Prepend new data (Newest on top)
            new_content = f"{raw_data}\n{current_content}"
            
            payload = {
                "files": {
                    target_file: {"content": new_content}
                }
            }
            
            requests.patch(f"https://api.github.com/gists/{_GID}", headers=h, json=payload)
            print("✅ System: Remote Storage Updated.")
        except Exception:
            print("⚠️ System: Storage Sync Failed.")

    def _mask(self, txt):
        """Masks data for logs (e.g., SVI123 -> SV****)"""
        if len(txt) > 4:
            return txt[:2] + "****" + txt[-2:]
        return "****"

    def _scan_stream(self, idx, encoded_url):
        try:
            url = _d(encoded_url)
            # Add random parameter to bypass cache
            url += f"&_={int(time.time()*1000)}"
            
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Parse logic based on your structure
                # Assuming simple list or nested 'data' key
                items = data if isinstance(data, list) else data.get('data', [])
                
                for item in items:
                    val = item.get('code') # The value we want
                    
                    if val and val not in self.seen:
                        # NEW DATA FOUND
                        is_special = val.startswith('SVG') or val.startswith('SVI') # Logic preservation
                        
                        print(f"\n🚨 NEW SIGNAL DETECTED [Stream {idx}]")
                        print(f"   🔑 Hash: {self._mask(val)}") # Masked Log
                        
                        self.seen.add(val)
                        self._push_update(val, is_special)
                        
        except Exception:
            pass # Silent fail to keep running

    def execute(self):
        print("🚀 System: Node Active. Monitoring Streams...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            while self.active:
                # Check runtime limit
                if time.time() - self.start_ts > _LIM:
                    print("\n🛑 System: Maintenance Cycle Reached.")
                    self.active = False
                    break
                
                # Launch scanners
                futures = []
                for i, ep in enumerate(_EPS):
                    futures.append(executor.submit(self._scan_stream, i, ep))
                
                # Wait for batch completion
                for f in futures:
                    f.result()
                
                # Wait before next poll
                time.sleep(_INT + random.random())

if __name__ == "__main__":
    node = DataNode()
    node.execute()