import requests
import json
import time
import os
import base64
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

GID_PRIMARY = os.getenv("GIST_ID_PRIMARY")
GID_KERNEL = os.getenv("GIST_ID_KERNEL")
GH_TOKEN = os.getenv("GH_TOKEN")

FILE_PRIMARY = "newCoupon.txt"
FILE_KERNEL = "lower500.txt"

ENCODED_URLS = [
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP3R5cGU9bG9nJmluZGV4TmFtZT1pbnRlcmVzdF9jZW50ZXJzJmxvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP2luZGV4TmFtZT1pbnRlcmVzdF9jZW50ZXJzJmxvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP2xvZ05hbWU9aW5mbyZ3ZWJJRD0yNTY0Nw==",
    "aHR0cHM6Ly9zZWFyY2gtbmV3LmJpdGJucy5jb20vYXV0b2NvdXBvbi1hcGlzL2dldFNpZGVCYXJDb3Vwb25zP3dlYklEPTI1NjQ3"
]

def get_ist_time():
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    return ist_now.strftime('%H:%M:%S.%f')[:-3]

class CloudCouponMonitor:
    def __init__(self):
        self.api_urls = [base64.b64decode(url).decode('utf-8') for url in ENCODED_URLS]
        self.seen_coupons = set()
        self.first_run = True
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        })

    def _mask_code(self, code):
        if not code or len(code) < 8: return "****"
        return f"{code[:4]}****{code[-2:]}"

    def _fetch_and_count_gist(self, gist_id, filename_label):
        count = 0
        if not gist_id or not GH_TOKEN:
            print(f"   ⚠️  Warning: Secrets missing for {filename_label}")
            return 0

        try:
            headers = {"Authorization": f"token {GH_TOKEN}"}
            r = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers)
            if r.status_code == 200:
                files = r.json().get('files', {})
                for fname, fcontent in files.items():
                    content = fcontent.get('content', '')
                    lines = content.split('\n')
                    for line in lines:
                        if line.strip():
                            self.seen_coupons.add(line.strip())
                            count += 1
                print(f"   📥  Verified {filename_label}: {count} coupons loaded.")
            else:
                print(f"   ❌  Failed to sync {filename_label} (HTTP {r.status_code})")
        except Exception as e:
            print(f"   ❌  Error syncing {filename_label}: {e}")
        return count

    def sync_initial_cache(self):
        print(f"☁️  Syncing Cloud Storage...")
        self._fetch_and_count_gist(GID_PRIMARY, FILE_PRIMARY)
        self._fetch_and_count_gist(GID_KERNEL, FILE_KERNEL)
        print(f"   📊 Total Cloud Cache: {len(self.seen_coupons)} unique codes ready.")

    def save_to_gist(self, code, is_kernel_type):
        target_gid = GID_KERNEL if is_kernel_type else GID_PRIMARY
        target_filename = FILE_KERNEL if is_kernel_type else FILE_PRIMARY
        
        if not target_gid or not GH_TOKEN:
            print(f"   ⚠️ Secrets Missing! Cannot save {self._mask_code(code)}")
            return

        try:
            headers = {"Authorization": f"token {GH_TOKEN}"}
            r = requests.get(f"https://api.github.com/gists/{target_gid}", headers=headers)
            current_content = ""
            actual_filename = target_filename
            
            if r.status_code == 200:
                files = r.json().get('files', {})
                if target_filename in files:
                    current_content = files[target_filename]['content']
                elif files:
                    actual_filename = list(files.keys())[0]
                    current_content = files[actual_filename]['content']
            
            new_content = f"{code}\n{current_content}"
            
            payload = {
                "files": {
                    actual_filename: {"content": new_content}
                }
            }
            requests.patch(f"https://api.github.com/gists/{target_gid}", headers=headers, json=payload)
            print(f"   💾 Saved to top of {actual_filename}", flush=True)
            
        except Exception as e:
            print(f"   ❌ Save Error: {e}", flush=True)

    def fetch_from_url(self, url_index, url):
        try:
            bust_url = f"{url}&_={int(time.time()*1000)}" 
            response = self.session.get(bust_url, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 1:
                    codes = data.get('codes', [])
                    return (url_index, codes) 
        except Exception:
            pass
        return (url_index, [])

    def check_updates(self):
        ts = get_ist_time()
        print(f"\r⚡ Scanning Sources... {ts}", end="", flush=True)
        
        fetched_results = []

        with ThreadPoolExecutor(max_workers=len(self.api_urls)) as executor:
            futures = [executor.submit(self.fetch_from_url, i+1, url) for i, url in enumerate(self.api_urls)]
            for future in futures:
                try:
                    fetched_results.append(future.result())
                except: pass

        if self.first_run:
            new_found_in_baseline = 0
            for _, codes in fetched_results:
                for item in codes:
                    code = item.get('code')
                    if code and code not in self.seen_coupons:
                        self.seen_coupons.add(code)
                        new_found_in_baseline += 1
            
            print(f"\n✅ Baseline established. Ignoring {len(self.seen_coupons)} existing coupons.", flush=True)
            self.first_run = False
            return

        for src_id, codes in fetched_results:
            for item in codes:
                code = item.get('code')
                
                if code and code not in self.seen_coupons:
                    self.seen_coupons.add(code)
                    
                    print(f"\n\n🚨 🔥 NEW COUPON DETECTED from URL #{src_id}!")
                    print(f"   🎟️ Code: {self._mask_code(code)}")
                    print(f"   ⏰ Time: {get_ist_time()}")
                    
                    is_special = code.upper().startswith("SVI") or code.upper().startswith("SVG")
                    self.save_to_gist(code, is_special)

    def run(self):
        print("\n" + "="*60)
        print("🚀 EXTREME SPEED COUPON SNIPER (SESSION + THREADS)")
        print("="*60)
        
        print(f"📡 Initializing Monitors...")
        for i in range(1, len(self.api_urls) + 1):
            print(f"   ✅ Monitor active for URL #{i}")
            
        print("\n⏳ Polling Strategy: 3s (Cloud Optimized)")
        print(f"📂 Default File: {FILE_PRIMARY}")
        print(f"📂 Special File (SVI/SVG): {FILE_KERNEL}")
        
        print("-" * 60)
        self.sync_initial_cache()
        print("="*60 + "\n")
        
        try:
            start_time = time.time()
            TIMEOUT = 21000 
            
            while True:
                if time.time() - start_time > TIMEOUT:
                    print("\n🛑 Maintenance Restart Triggered.")
                    break
                    
                self.check_updates()
                time.sleep(3) 
                
        except KeyboardInterrupt:
            print("\n👋 Monitor Stopped.")

if __name__ == "__main__":
    monitor = CloudCouponMonitor()
    monitor.run()
