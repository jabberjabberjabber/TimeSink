import json
import os
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

import config as cfg_module


def _get_sessions():
    if not os.path.exists(cfg_module.SESSIONS_DIR):
        return []
    entries = []
    for d in os.listdir(cfg_module.SESSIONS_DIR):
        if os.path.isdir(os.path.join(cfg_module.SESSIONS_DIR, d)):
            entries.append(d)
    return sorted(entries, reverse=True)


def _load_annotations(session_dir):
    path = os.path.join(session_dir, "annotations.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}


def _get_images(session_dir):
    return sorted(
        f for f in os.listdir(session_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )


def run_annotator():
    sessions = _get_sessions()
    if not sessions:
        print("No sessions found.")
        return

    root = tk.Tk()
    root.title("TimeSink Annotator")
    root.geometry("1020x720")
    root.resizable(True, True)

    # ── state ──────────────────────────────────────────────────────────────
    state = {
        "session_dir": None,
        "images": [],
        "index": 0,
        "annotations": {},
        "photo": None,
    }

    # ── helpers ────────────────────────────────────────────────────────────
    def _load_session(name):
        sd = os.path.join(cfg_module.SESSIONS_DIR, name)
        state["session_dir"] = sd
        state["images"] = _get_images(sd)
        state["index"] = 0
        state["annotations"] = _load_annotations(sd)
        _show_image()
        status_var.set("")

    def _save_annotations():
        path = os.path.join(state["session_dir"], "annotations.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state["annotations"], f, indent=2)

    def _show_image():
        if not state["images"]:
            canvas.delete("all")
            lbl_info.config(text="No images in session.")
            txt.delete("1.0", tk.END)
            return

        idx = state["index"]
        name = state["images"][idx]
        lbl_info.config(text=f"{name}  ({idx + 1} / {len(state['images'])})")

        img = Image.open(os.path.join(state["session_dir"], name))
        cw = canvas.winfo_width() or 960
        ch = canvas.winfo_height() or 560
        img.thumbnail((cw, ch), Image.LANCZOS)
        state["photo"] = ImageTk.PhotoImage(img)
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=state["photo"])

        txt.delete("1.0", tk.END)
        txt.insert("1.0", state["annotations"].get(name, ""))

    def _commit_annotation():
        if not state["images"]:
            return
        name = state["images"][state["index"]]
        text = txt.get("1.0", tk.END).strip()
        if text:
            state["annotations"][name] = text
        elif name in state["annotations"]:
            del state["annotations"][name]
        _save_annotations()
        status_var.set("Saved.")

    def _go(delta):
        _commit_annotation()
        new_idx = state["index"] + delta
        if 0 <= new_idx < len(state["images"]):
            state["index"] = new_idx
            _show_image()
        status_var.set("")

    def _on_session_change(_event=None):
        _load_session(session_var.get())

    def _on_resize(_event=None):
        _show_image()

    # ── layout ─────────────────────────────────────────────────────────────
    top = tk.Frame(root, pady=4)
    top.pack(fill=tk.X, padx=8)

    tk.Label(top, text="Session:").pack(side=tk.LEFT)
    session_var = tk.StringVar(value=sessions[0])
    combo = ttk.Combobox(top, textvariable=session_var, values=sessions,
                         state="readonly", width=32)
    combo.pack(side=tk.LEFT, padx=6)
    combo.bind("<<ComboboxSelected>>", _on_session_change)

    lbl_info = tk.Label(top, text="", fg="#555")
    lbl_info.pack(side=tk.LEFT, padx=12)

    canvas = tk.Canvas(root, bg="#1a1a1a", cursor="arrow")
    canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
    canvas.bind("<Configure>", _on_resize)

    bot = tk.Frame(root, pady=4)
    bot.pack(fill=tk.X, padx=8)

    tk.Button(bot, text="◀  Back", width=10,
              command=lambda: _go(-1)).pack(side=tk.LEFT)
    tk.Button(bot, text="Next  ▶", width=10,
              command=lambda: _go(1)).pack(side=tk.LEFT, padx=4)

    txt = tk.Text(bot, height=3, width=64, wrap=tk.WORD)
    txt.pack(side=tk.LEFT, padx=8)

    right = tk.Frame(bot)
    right.pack(side=tk.LEFT)
    tk.Button(right, text="Save", width=10,
              command=_commit_annotation).pack()
    status_var = tk.StringVar()
    tk.Label(right, textvariable=status_var, fg="#2a9d2a", width=10).pack()

    # ── key bindings ───────────────────────────────────────────────────────
    root.bind("<Left>", lambda e: _go(-1))
    root.bind("<Right>", lambda e: _go(1))
    root.bind("<Control-s>", lambda e: _commit_annotation())

    # ── init ───────────────────────────────────────────────────────────────
    _load_session(sessions[0])
    root.mainloop()
