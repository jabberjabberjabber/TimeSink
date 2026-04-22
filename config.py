import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
KCPPT_FILE = os.path.join(BASE_DIR, "timesink.kcppt")
KCPPT_TEMPLATE = os.path.join(BASE_DIR, "template.kcppt")
MODEL_LIST_FILE = os.path.join(BASE_DIR, "model_list.json")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
KOBOLDCPP_EXE = os.path.join(BASE_DIR, "koboldcpp.exe")
KOBOLDCPP_URL = "https://github.com/LostRuins/koboldcpp/releases/latest/download/koboldcpp.exe"

CONFIG_DEFAULTS = {
    "time_chunk": 15,
    "screenshot_interval": 60,
    "batch_size": 2,
    "max_tokens": 2048,
    "screenshot_prompt": (
        "Describe what is being worked on in this screenshot in general terms in a single sentence. For instance if an gmail is open, write that email is being attended to; if Teams is open, respond that they are in a meeting or in a conference call; etc."
    ),
    "chunk_prompt": (
        "Collect the work activity from the descriptions and compose a brief time log entry."
    ),
    "koboldcpp_url": "http://localhost:5001",
    "whispermodel": "https://huggingface.co/koboldcpp/whisper/resolve/main/whisper-base.en-q5_1.bin",
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(CONFIG_DEFAULTS.copy())
        return CONFIG_DEFAULTS.copy()
    with open(CONFIG_FILE, encoding="utf-8") as f:
        data = json.load(f)
    changed = False
    for k, v in CONFIG_DEFAULTS.items():
        if k not in data:
            data[k] = v
            changed = True
    if changed:
        save_config(data)
    return data


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_kcppt():
    if os.path.exists(KCPPT_FILE):
        with open(KCPPT_FILE, encoding="utf-8") as f:
            return json.load(f)
    # Bootstrap from template if available
    if os.path.exists(KCPPT_TEMPLATE):
        with open(KCPPT_TEMPLATE, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "port": 5001,
            "contextsize": 16384,
            "gpulayers": -1,
            "batchsize": 512,
            "multiuser": 1,
            "visionmaxres": 1500,
            "defaultgenamt": 768,
            "istemplate": False,
            "singleinstance": True,
            "launcher": False,
        }
    # Clear model-specific fields; remove config field
    data.pop("config", None)
    data["model_param"] = ""
    data["mmproj"] = ""
    data["chatcompletionsadapter"] = "AutoGuess"
    data["flashattention"] = True
    data["whispermodel"] = ""
    data["istemplate"] = False
    save_kcppt(data)
    return data


def save_kcppt(data):
    with open(KCPPT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_model_list():
    with open(MODEL_LIST_FILE, encoding="utf-8") as f:
        return json.load(f)
