import json
import os
import time
from datetime import datetime

from PIL import ImageGrab

import config as cfg_module


def run_screen_logger(cfg):
    interval = cfg["screenshot_interval"]
    session_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = os.path.join(cfg_module.SESSIONS_DIR, session_name)
    os.makedirs(session_dir, exist_ok=True)

    ann_file = os.path.join(session_dir, "annotations.json")
    with open(ann_file, "w", encoding="utf-8") as f:
        json.dump({}, f)

    print(f"\nSession: {session_name}")
    print(f"Saving to: {session_dir}")
    print(f"Interval: {interval}s  |  Press Ctrl+C to stop.\n")

    count = 0
    try:
        while True:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filepath = os.path.join(session_dir, f"{ts}.png")
            ImageGrab.grab().save(filepath)
            count += 1
            print(f"[{count}] {ts}.png")
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\nStopped. {count} screenshots in: {session_dir}")
