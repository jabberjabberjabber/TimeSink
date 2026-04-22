import os
import sys
import urllib.request

import config
from annotator import run_annotator
from dictation import run_dictation
from screen_logger import run_screen_logger
from summarizer import run_summarizer


# ── KoboldCPP download ─────────────────────────────────────────────────────────

def _download_koboldcpp():
    print("Downloading KoboldCPP...")

    def _progress(count, block, total):
        if total > 0:
            pct = min(count * block * 100 // total, 100)
            print(f"\r  {pct}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(config.KOBOLDCPP_URL, config.KOBOLDCPP_EXE, _progress)
        print("\nDownload complete.")
    except Exception as exc:
        print(f"\nDownload failed: {exc}")


# ── params sub-menu ────────────────────────────────────────────────────────────

def _set_model():
    models = config.load_model_list()
    print("\nAvailable models:")
    for i, m in enumerate(models):
        print(f"  {i + 1:2}.  {m['model']:40s}  ~{m['size_mb']:>5} MB  {m['description']}")

    choice = input("\nModel number (Enter to cancel): ").strip()
    if not choice:
        return
    try:
        idx = int(choice) - 1
        assert 0 <= idx < len(models)
    except (ValueError, AssertionError):
        print("Invalid selection.")
        return

    m = models[idx]
    cfg = config.load_config()
    kcppt = config.load_kcppt()
    kcppt.pop("config", None)
    kcppt["model_param"] = m["language_url"]
    kcppt["mmproj"] = m["mmproj_url"]
    kcppt["chatcompletionsadapter"] = m["adapter"]
    kcppt["flashattention"] = m["flashattention"]
    kcppt["whispermodel"] = cfg["whispermodel"]
    config.save_kcppt(kcppt)
    print(f"Model set to: {m['model']}")


def _prompt_int(label, current):
    val = input(f"{label} [{current}]: ").strip()
    if not val:
        return current
    try:
        return int(val)
    except ValueError:
        print("Invalid value — unchanged.")
        return current


def _prompt_str(label, current):
    print(f"Current: {current}")
    val = input(f"{label} (Enter to keep): ").strip()
    return val if val else current


def _params_menu():
    while True:
        cfg = config.load_config()
        kcppt = config.load_kcppt()
        model_name = kcppt.get("model_param") or "(none)"
        if len(model_name) > 60:
            model_name = "..." + model_name[-57:]

        print(f"""
--- Set Params ---
  1.  Set model              [{model_name}]
  2.  Time chunk (min)       [{cfg['time_chunk']}]
  3.  Screenshot interval (s) [{cfg['screenshot_interval']}]
  4.  Batch size             [{cfg['batch_size']}]
  5.  Max tokens             [{cfg['max_tokens']}]
  6.  Screenshot prompt
  7.  Chunk prompt
  8.  Back""")

        choice = input("\nChoice: ").strip()
        if choice == "1":
            _set_model()
        elif choice == "2":
            cfg["time_chunk"] = _prompt_int("Time chunk in minutes", cfg["time_chunk"])
            config.save_config(cfg)
        elif choice == "3":
            cfg["screenshot_interval"] = _prompt_int("Interval in seconds", cfg["screenshot_interval"])
            config.save_config(cfg)
        elif choice == "4":
            cfg["batch_size"] = _prompt_int("Batch size", cfg["batch_size"])
            config.save_config(cfg)
        elif choice == "5":
            cfg["max_tokens"] = _prompt_int("Max tokens", cfg["max_tokens"])
            config.save_config(cfg)
        elif choice == "6":
            cfg["screenshot_prompt"] = _prompt_str("Screenshot prompt", cfg["screenshot_prompt"])
            config.save_config(cfg)
        elif choice == "7":
            cfg["chunk_prompt"] = _prompt_str("Chunk prompt", cfg["chunk_prompt"])
            config.save_config(cfg)
        elif choice == "8":
            break
        else:
            print("Invalid choice.")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(config.SESSIONS_DIR, exist_ok=True)
    config.load_kcppt()   # create timesink.kcppt if absent
    config.load_config()  # create config.json if absent

    if not os.path.exists(config.KOBOLDCPP_EXE):
        print("Missing Koboldcpp.")
        _download_koboldcpp()

    while True:
        print("""
=== TimeSink ===
  1.  Set params
  2.  Launch screen logger
  3.  Launch annotator
  4.  Launch summarizer
  5.  Dictation
  6.  Exit""")

        choice = input("\nChoice: ").strip()
        if choice == "1":
            _params_menu()
        elif choice == "2":
            run_screen_logger(config.load_config())
        elif choice == "3":
            run_annotator()
        elif choice == "4":
            run_summarizer(config.load_config())
        elif choice == "5":
            run_dictation(config.load_config())
        elif choice == "6":
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
