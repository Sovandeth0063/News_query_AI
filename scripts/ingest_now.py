import time
import sys
from pathlib import Path

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sync_manager import sync_manager

if __name__ == "__main__":
    print("==================================================")
    print("Starting manual news ingestion pipeline...")
    print("==================================================")
    run_id = sync_manager.run_sync_background(trigger="manual_cli")

    while True:
        status = sync_manager.get_status()
        pct = status.get("percent", 0)
        msg = status.get("message", "")
        print(f"[{pct}%] {msg}", flush=True)

        if status.get("status") in ["completed", "failed"]:
            stats = status.get("stats", {})
            print("--------------------------------------------------", flush=True)
            print(f"Finished with status: {status.get('status').upper()}", flush=True)
            print(f"Fetched:  {stats.get('fetched', 0)}", flush=True)
            print(f"New:      {stats.get('new', 0)}", flush=True)
            print(f"Dupes:    {stats.get('dupes', 0)}", flush=True)
            print(f"Failed:   {stats.get('failed', 0)}", flush=True)
            print("--------------------------------------------------", flush=True)
            break
        time.sleep(1.5)

