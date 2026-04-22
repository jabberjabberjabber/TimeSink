import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import config as cfg_module


# ── image helpers ──────────────────────────────────────────────────────────────

def _encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _mime(path):
    return "image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png"


def _parse_ts(filename):
    try:
        return datetime.strptime(os.path.splitext(filename)[0], "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


# ── API ────────────────────────────────────────────────────────────────────────

def _api_chat(url, messages, max_tokens=2048, max_retries=3):
    payload = json.dumps({
        "model": "koboldcpp",
        "messages": messages,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{url}/v1/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            if attempt < max_retries - 1:
                print(f"  Retry ({attempt + 1}/{max_retries - 1}): {exc}")
                time.sleep(3)
            else:
                raise


def _wait_for_api(url, timeout=300):
    print("Waiting for KoboldCPP", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{url}/api/extra/version", timeout=4)
            print(" ready.")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(3)
    print(" timed out.")
    return False


# ── session helpers ────────────────────────────────────────────────────────────

def _get_sessions():
    if not os.path.exists(cfg_module.SESSIONS_DIR):
        return []
    out = []
    for d in os.listdir(cfg_module.SESSIONS_DIR):
        if os.path.isdir(os.path.join(cfg_module.SESSIONS_DIR, d)):
            out.append(d)
    return sorted(out, reverse=True)


def _load_annotations(session_dir):
    path = os.path.join(session_dir, "annotations.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}


def _build_batch_messages(batch, session_dir, annotations, prompt):
    timestamps = []
    for name in batch:
        ts = _parse_ts(name)
        timestamps.append(ts.strftime("%H:%M:%S") if ts else name)

    ann_lines = []
    for name, ts_str in zip(batch, timestamps):
        note = annotations.get(name, "").strip()
        if note:
            ann_lines.append(f"{ts_str}: {note}")

    text = f"Screenshots taken at: {', '.join(timestamps)}\n\n{prompt}"
    if ann_lines:
        text += "\n\nUser annotations:\n" + "\n".join(ann_lines)

    content = [{"type": "text", "text": text}]
    for name in batch:
        b64 = _encode_image(os.path.join(session_dir, name))
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{_mime(name)};base64,{b64}"},
        })
    return [{"role": "user", "content": content}]


def _save_generations(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── main entry ────────────────────────────────────────────────────────────────

def run_summarizer(cfg):
    sessions = _get_sessions()
    if not sessions:
        print("No sessions found.")
        return

    print("\nAvailable sessions:")
    for i, s in enumerate(sessions):
        print(f"  {i + 1}. {s}")

    choice = input("\nSelect session number (or Enter to cancel): ").strip()
    if not choice:
        return
    try:
        idx = int(choice) - 1
        assert 0 <= idx < len(sessions)
    except (ValueError, AssertionError):
        print("Invalid selection.")
        return

    session_name = sessions[idx]
    session_dir = os.path.join(cfg_module.SESSIONS_DIR, session_name)

    annotations = _load_annotations(session_dir)

    images = sorted(
        f for f in os.listdir(session_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )
    if not images:
        print("No images in session.")
        return

    if not os.path.exists(cfg_module.KOBOLDCPP_EXE):
        print("koboldcpp.exe not found. Download it from the main menu first.")
        return

    kcppt = cfg_module.load_kcppt()
    if not kcppt.get("model_param"):
        print("No model selected. Set a model in params first.")
        return

    api_url = cfg.get("koboldcpp_url", "http://localhost:5001")

    # Start KoboldCPP only if API isn't already up
    proc = None
    try:
        urllib.request.urlopen(f"{api_url}/api/extra/version", timeout=3)
        print("KoboldCPP already running.")
    except Exception:
        print("Starting KoboldCPP...")
        proc = subprocess.Popen(
            [cfg_module.KOBOLDCPP_EXE, "--config", cfg_module.KCPPT_FILE],
            cwd=cfg_module.BASE_DIR,
        )
        if not _wait_for_api(api_url):
            print("Failed to connect to KoboldCPP.")
            proc.terminate()
            return

    gen_file = os.path.join(session_dir, "generations.json")
    if os.path.exists(gen_file):
        with open(gen_file, encoding="utf-8") as f:
            generations = json.load(f)
    else:
        generations = {"batches": [], "chunks": []}

    batch_size = cfg["batch_size"]
    chunk_minutes = cfg["time_chunk"]
    max_tokens = cfg["max_tokens"]
    screenshot_prompt = cfg["screenshot_prompt"]
    chunk_prompt = cfg["chunk_prompt"]

    first_ts = _parse_ts(images[0])
    if not first_ts:
        print("Cannot parse timestamps from image filenames.")
        return

    chunk_start = first_ts
    chunk_end = chunk_start + timedelta(minutes=chunk_minutes)
    pending_gens = []   # (first_ts, last_ts, text) per batch in current chunk
    chunk_summaries = []

    total_batches = (len(images) + batch_size - 1) // batch_size
    print(f"\nProcessing {len(images)} images in {total_batches} batch(es) of {batch_size}...\n")

    for b_idx, start in enumerate(range(0, len(images), batch_size)):
        batch = images[start: start + batch_size]
        label = f"Batch {b_idx + 1}/{total_batches}  [{batch[0]}–{batch[-1]}]"
        print(f"  {label}...", end="", flush=True)

        messages = _build_batch_messages(batch, session_dir, annotations, screenshot_prompt)
        try:
            text = _api_chat(api_url, messages, max_tokens=512)
            print(" done.")
        except Exception as exc:
            text = f"[Error: {exc}]"
            print(f" error: {exc}")

        first_ts_batch = _parse_ts(batch[0])
        last_ts = _parse_ts(batch[-1])
        generations["batches"].append({
            "type": "batch",
            "images": batch,
            "timestamp": last_ts.isoformat() if last_ts else None,
            "text": text,
        })
        _save_generations(gen_file, generations)
        pending_gens.append((first_ts_batch, last_ts, text))

        # Flush chunk summaries when we pass the chunk boundary
        if last_ts and last_ts >= chunk_end:
            while last_ts >= chunk_end:
                label_c = f"{chunk_start.strftime('%H:%M')}–{chunk_end.strftime('%H:%M')}"
                print(f"  Summarising chunk {label_c}...", end="", flush=True)
                combined = "\n\n".join(
                    f"[{ft.strftime('%H:%M:%S')}–{lt.strftime('%H:%M:%S')}]\n{t}"
                    for ft, lt, t in pending_gens
                )
                chunk_msgs = [{"role": "user", "content": [
                    {"type": "text", "text": f"{chunk_prompt}\n\n{combined}"}
                ]}]
                try:
                    summary = _api_chat(api_url, chunk_msgs, max_tokens)
                    print(" done.")
                except Exception as exc:
                    summary = combined
                    print(f" error: {exc}")

                generations["chunks"].append({
                    "type": "chunk",
                    "start": chunk_start.isoformat(),
                    "end": chunk_end.isoformat(),
                    "text": summary,
                })
                _save_generations(gen_file, generations)
                chunk_summaries.append((chunk_start, chunk_end, summary))

                chunk_start = chunk_end
                chunk_end = chunk_start + timedelta(minutes=chunk_minutes)
                pending_gens = []

    # Final partial chunk
    if pending_gens:
        label_c = f"{chunk_start.strftime('%H:%M')}–{chunk_end.strftime('%H:%M')}"
        print(f"  Summarising final chunk {label_c}...", end="", flush=True)
        combined = "\n\n".join(
            f"[{ft.strftime('%H:%M:%S')}–{lt.strftime('%H:%M:%S')}]\n{t}"
            for ft, lt, t in pending_gens
        )
        chunk_msgs = [{"role": "user", "content": [
            {"type": "text", "text": f"{chunk_prompt}\n\n{combined}"}
        ]}]
        try:
            summary = _api_chat(api_url, chunk_msgs)
            print(" done.")
        except Exception as exc:
            summary = combined
            print(f" error: {exc}")

        generations["chunks"].append({
            "type": "chunk",
            "start": chunk_start.isoformat(),
            "end": chunk_end.isoformat(),
            "text": summary,
        })
        _save_generations(gen_file, generations)
        chunk_summaries.append((chunk_start, chunk_end, summary))

    # Export CSV
    csv_path = os.path.join(session_dir, f"{session_name}_summary.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("Start,End,Summary\n")
        for s, e, t in chunk_summaries:
            clean = t.replace('"', '""').replace("\n", " ")
            f.write(f'"{s.strftime("%H:%M")}","{e.strftime("%H:%M")}","{clean}"\n')

    print(f"\nDone. Summary: {csv_path}")

    if proc:
        ans = input("Shut down KoboldCPP? (y/n): ").strip().lower()
        if ans == "y":
            proc.terminate()
            print("KoboldCPP stopped.")
