import requests
import json
import time
import os
import base64
import random
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 🔒 SYSTEM CONFIGURATION
# ==========================================
_GID1 = os.getenv("GIST_ID_PRIMARY") 
_GID2 = os.getenv("GIST_ID_KERNEL")
_GTK = os.getenv("GH_TOKEN")

_F1 = "sys_log_primary.txt" 
_F2 = "sys_log_kernel.txt"

# Hidden Endpoints
_EPS = [
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP3R5cGU9bG9nJmluZGV4TmFtZT1pbnRlcmVzdF9jZW50ZXJzJmxvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP2luZGV4TmFtZT1pbnRlcmVzdF9jZW50ZXJzJmxvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP2xvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP3dlYklEPTI1NjQ3"
]

_LIM = 21000 
_INT = 3 # FAST POLLING (3 Seconds)

_d = lambda b: base64.b64decode(b).decode('utf-8')

class DataNode:
    def __init__(self):
        self.seen = set()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        })
        self.start_ts = time.time()
        self.active = True
        self._load_cache()

    def _load_cache(self):
        print("System: Syncing Cache...")
        if not _GTK: return

        h = {"Authorization": f"token {_GTK}"}
        
        if _GID1:
            try:
                r = requests.get(f"https://api.github.com/gists/{_GID1}", headers=h)
                if r.status_code == 200:
                    files = r.json().get('files', {})
                    target_file = _F1 if _F1 in files else list(files.keys())[0]
                    c1 = files[target_file]['content'].split('\n')
                    self.seen.update([x.strip() for x in c1 if x.strip()])
            except: pass

        if _GID2:
            try:
                r = requests.get(f"https://api.github.com/gists/{_GID2}", headers=h)
                if r.status_code == 200:
                    files = r.json().get('files', {})
                    target_file = _F2 if _F2 in files else list(files.keys())[0]
                    c2 = files[target_file]['content'].split('\n')
                    self.seen.update([x.strip() for x in c2 if x.strip()])
            except: pass
            
        print(f"System: Cache Loaded ({len(self.seen)} nodes).")

    def _push_update(self, raw_data, is_special):
        if not _GTK: return
        
        target_gid = _GID2 if is_special else _GID1
        target_file = _F2 if is_special else _F1
        
        if not target_gid: return

        try:
            h = {"Authorization": f"token {_GTK}"}
            r = requests.get(f"https://api.github.com/gists/{target_gid}", headers=h)
            current_content = ""
            actual_filename = target_file
            
            if r.status_code == 200:
                files = r.json().get('files', {})
                if target_file in files:
                    actual_filename = target_file
                    current_content = files[target_file]['content']
                elif files:
                    actual_filename = list(files.keys())[0]
                    current_content = files[actual_filename]['content']
            
            new_content = f"{raw_data}\n{current_content}"
            payload = {"files": {actual_filename: {"content": new_content}}}
            
            requests.patch(f"https://api.github.com/gists/{target_gid}", headers=h, json=payload)
            print("✅ System: Remote Storage Updated.")
        except Exception:
            print("⚠️ System: Storage Sync Failed.")

    def _mask(self, txt):
        if len(txt) > 4: return txt[:2] + "****" + txt[-2:]
        return "****"

    def _scan_stream(self, idx, encoded_url):
        try:
            url = _d(encoded_url)
            url += f"&_={int(time.time()*1000)}"
            
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get('data', [])
                
                for item in items:
                    val = item.get('code')
                    if val and val not in self.seen:
                        is_special = val.startswith('SVG') or val.startswith('SVI')
                        
                        ts = datetime.now().strftime('%H:%M:%S')
                        print(f"\n[{ts}] 🚨 NEW SIGNAL [Stream {idx}]: {self._mask(val)}")
                        
                        self.seen.add(val)
                        self._push_update(val, is_special)
        except Exception: pass

    def execute(self):
        print("🚀 System: Node Active. High Frequency Mode.")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            while self.active:
                if time.time() - self.start_ts > _LIM:
                    print("\n🛑 System: Maintenance Cycle Reached.")
                    self.active = False
                    break
                
                # Live Timestamp Log to show speed
                ts = datetime.now().strftime('%H:%M:%S')
                print(f"[{ts}] ⚡ Scanning Streams...", end='\r')

                futures = []
                for i, ep in enumerate(_EPS):
                    futures.append(executor.submit(self._scan_stream, i, ep))
                
                for f in futures:
                    try: f.result()
                    except: pass
                
                time.sleep(_INT)

if __name__ == "__main__":
    node = DataNode()
    node.execute()
