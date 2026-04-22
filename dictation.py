import json
import os
import subprocess
import time
import urllib.request
import uuid
from datetime import datetime, timedelta

import config as cfg_module
from summarizer import _api_chat, _get_sessions, _save_generations, _wait_for_api


# ── dictations.json helpers ───────────────────────────────────────────────────

def _load_dictations(session_dir):
    path = os.path.join(session_dir, "dictations.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}


def _save_dictations(session_dir, data):
    path = os.path.join(session_dir, "dictations.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── timestamp parsing ─────────────────────────────────────────────────────────

def _session_date(session_name):
    """Extract the date from a session folder name, falling back to today."""
    try:
        return datetime.strptime(session_name, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_ts(ts_str, base_date):
    """Parse a user-supplied timestamp string into a datetime.

    Accepts full datetimes or time-only strings; time-only entries are anchored
    to base_date so they sort correctly against each other.
    """
    for fmt in ("%Y-%m-%d_%H-%M-%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    for fmt in ("%H-%M-%S", "%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(ts_str, fmt)
            return base_date.replace(
                hour=t.hour, minute=t.minute, second=t.second, microsecond=0
            )
        except ValueError:
            continue
    return None


# ── transcription API ─────────────────────────────────────────────────────────

def _transcribe(url, filepath, max_retries=3):
    """Send a WAV file to /v1/audio/transcriptions via multipart/form-data."""
    with open(filepath, "rb") as f:
        audio_data = f.read()

    boundary = uuid.uuid4().hex
    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += (
        f'Content-Disposition: form-data; name="file"; '
        f'filename="{os.path.basename(filepath)}"\r\n'
    ).encode()
    body += b"Content-Type: audio/wav\r\n\r\n"
    body += audio_data
    body += b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
    body += b"whisper\r\n"
    body += f"--{boundary}--\r\n".encode()

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{url}/v1/audio/transcriptions",
                data=bytes(body),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))["text"].strip()
        except Exception as exc:
            if attempt < max_retries - 1:
                print(f"  Retry ({attempt + 1}/{max_retries - 1}): {exc}")
                time.sleep(3)
            else:
                raise


# ── main entry ────────────────────────────────────────────────────────────────

def run_dictation(cfg):
    sessions = _get_sessions()
    if not sessions:
        print("No sessions found.")
        return

    print("\nAvailable sessions:")
    for i, s in enumerate(sessions):
        print(f"  {i + 1}. {s}")

    choice = input("\nSelect session (or Enter to cancel): ").strip()
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
    base_date = _session_date(session_name)

    wav_files = sorted(
        f for f in os.listdir(session_dir)
        if f.lower().endswith(".wav")
    )
    if not wav_files:
        print("No WAV files in session.")
        return

    dictations = _load_dictations(session_dir)

    # ── collect timestamps upfront ────────────────────────────────────────────
    pending = []  # [(wav_filename, ts_str)]
    print("\nEnter a timestamp for each WAV (HH:MM:SS, or Enter to use the filename):")
    for wav in wav_files:
        if wav in dictations:
            print(f"  {wav}: already transcribed, skipping")
            continue
        default = os.path.splitext(wav)[0]
        entered = input(f"  {wav} [{default}]: ").strip()
        pending.append((wav, entered if entered else default))

    # ── transcribe ────────────────────────────────────────────────────────────
    if pending:
        # Ensure whispermodel is written into the kcppt before launch
        kcppt = cfg_module.load_kcppt()
        kcppt["whispermodel"] = cfg.get("whispermodel", "")
        cfg_module.save_kcppt(kcppt)

        api_url = cfg.get("koboldcpp_url", "http://localhost:5001")
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

        for wav, ts_str in pending:
            print(f"  Transcribing {wav}...", end="", flush=True)
            try:
                text = _transcribe(api_url, os.path.join(session_dir, wav))
                dictations[ts_str] = text
                _save_dictations(session_dir, dictations)
                print(" done.")
            except Exception as exc:
                print(f" error: {exc}")
    else:
        print("Nothing new to transcribe.")
        api_url = cfg.get("koboldcpp_url", "http://localhost:5001")
        proc = None

    if not dictations:
        return

    # ── chunk summarisation ───────────────────────────────────────────────────
    print("\nSummarising dictations...")

    sorted_entries = sorted(
        ((_parse_ts(ts, base_date), ts, text) for ts, text in dictations.items()),
        key=lambda x: (x[0] is None, x[0]),
    )

    first_dt = next((dt for dt, _, _ in sorted_entries if dt), None)
    if not first_dt:
        print("Could not parse any timestamps for summarisation.")
        return

    chunk_minutes = cfg["time_chunk"]
    max_tokens = cfg["max_tokens"]
    chunk_prompt = cfg["chunk_prompt"]

    gen_file = os.path.join(session_dir, "generations.json")
    try:
        with open(gen_file, encoding="utf-8") as f:
            generations = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        generations = {"batches": [], "chunks": []}

    chunk_start = first_dt
    chunk_end = chunk_start + timedelta(minutes=chunk_minutes)
    pending_chunk = []   # [(dt, text)]
    chunk_summaries = []

    def _flush(cs, ce, pc):
        if not pc:
            return None
        label = f"{cs.strftime('%H:%M')}–{ce.strftime('%H:%M')}"
        print(f"  Chunk {label}...", end="", flush=True)
        combined = "\n\n".join(
            f"[{dt.strftime('%H:%M:%S')}]\n{t}" for dt, t in pc
        )
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": f"{chunk_prompt}\n\n{combined}"}
        ]}]
        try:
            summary = _api_chat(api_url, msgs, max_tokens)
            print(" done.")
        except Exception as exc:
            summary = combined
            print(f" error: {exc}")
        generations["chunks"].append({
            "type": "chunk",
            "source": "dictation",
            "start": cs.isoformat(),
            "end": ce.isoformat(),
            "text": summary,
        })
        _save_generations(gen_file, generations)
        return (cs, ce, summary)

    for dt, _ts_str, text in sorted_entries:
        if dt and dt >= chunk_end:
            result = _flush(chunk_start, chunk_end, pending_chunk)
            if result:
                chunk_summaries.append(result)
            while dt >= chunk_end:
                chunk_start = chunk_end
                chunk_end = chunk_start + timedelta(minutes=chunk_minutes)
            pending_chunk = []
        pending_chunk.append((dt or chunk_start, text))

    result = _flush(chunk_start, chunk_end, pending_chunk)
    if result:
        chunk_summaries.append(result)

    if not chunk_summaries:
        return

    # ── append to CSV ─────────────────────────────────────────────────────────
    csv_path = os.path.join(session_dir, f"{session_name}_summary.csv")
    mode = "a" if os.path.exists(csv_path) else "w"
    with open(csv_path, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("Start,End,Summary\n")
        for s, e, t in chunk_summaries:
            clean = t.replace('"', '""').replace("\n", " ")
            f.write(f'"{s.strftime("%H:%M")}","{e.strftime("%H:%M")}","{clean}"\n')

    print(f"\nDictation summary appended to: {csv_path}")

    if proc:
        ans = input("Shut down KoboldCPP? (y/n): ").strip().lower()
        if ans == "y":
            proc.terminate()
            print("KoboldCPP stopped.")
