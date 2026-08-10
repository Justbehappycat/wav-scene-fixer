#!/usr/bin/env python3
"""Tkinter GUI wrapper around wav_scene_fix.py — batch-clean BWF scene names."""

import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wav_scene_fix as wsf

SETTINGS_PATH = os.path.expanduser("~/.wav_scene_fixer.json")
FPS_CHOICES = ["(unchanged)"] + list(wsf.FPS_TABLE)


class App:
    def __init__(self, root):
        self.root = root
        root.title("WAV Scene Fixer")
        root.minsize(640, 480)
        self.log_queue = queue.Queue()
        self.worker = None

        s = self.load_settings()
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(root)
        frm.pack(fill="x", **pad)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Input folder:").grid(row=0, column=0, sticky="w")
        self.in_var = tk.StringVar(value=s.get("input", ""))
        ttk.Entry(frm, textvariable=self.in_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(frm, text="Choose…", command=self.pick_input).grid(row=0, column=2)

        ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w")
        self.out_var = tk.StringVar(value=s.get("output", ""))
        ttk.Entry(frm, textvariable=self.out_var).grid(row=1, column=1, sticky="ew")
        ttk.Button(frm, text="Choose…", command=self.pick_output).grid(row=1, column=2)
        ttk.Label(frm, text="(empty = <input>/cleaned — originals are never modified)",
                  foreground="gray").grid(row=2, column=1, sticky="w")

        ttk.Label(frm, text="Frame rate:").grid(row=3, column=0, sticky="w")
        self.fps_var = tk.StringVar(value=s.get("fps", FPS_CHOICES[0]))
        ttk.Combobox(frm, textvariable=self.fps_var, values=FPS_CHOICES,
                     state="readonly", width=14).grid(row=3, column=1, sticky="w")

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.preview_btn = ttk.Button(btns, text="Preview (dry run)",
                                      command=lambda: self.start(dry_run=True))
        self.preview_btn.pack(side="left")
        self.run_btn = ttk.Button(btns, text="Process files",
                                  command=lambda: self.start(dry_run=False))
        self.run_btn.pack(side="left", padx=8)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(btns, textvariable=self.status_var, foreground="gray").pack(side="right")

        self.log = tk.Text(root, height=18, state="disabled",
                           font=("Menlo", 11), wrap="none")
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        root.after(100, self.drain_log)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -- settings ---------------------------------------------------------
    def load_settings(self):
        try:
            with open(SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self):
        try:
            with open(SETTINGS_PATH, "w") as f:
                json.dump({
                    "input": self.in_var.get(), "output": self.out_var.get(),
                    "fps": self.fps_var.get(),
                }, f, indent=2)
        except Exception:
            pass

    # -- UI helpers -------------------------------------------------------
    def pick_input(self):
        d = filedialog.askdirectory(title="Folder with WAV files")
        if d:
            self.in_var.set(d)

    def pick_output(self):
        d = filedialog.askdirectory(title="Output folder for cleaned copies")
        if d:
            self.out_var.set(d)

    def emit(self, line):
        self.log_queue.put(line)

    def drain_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line is None:  # worker finished
                    self.preview_btn["state"] = self.run_btn["state"] = "normal"
                    self.status_var.set("Done")
                    continue
                self.log["state"] = "normal"
                self.log.insert("end", line + "\n")
                self.log.see("end")
                self.log["state"] = "disabled"
        except queue.Empty:
            pass
        self.root.after(100, self.drain_log)

    def on_close(self):
        self.save_settings()
        self.root.destroy()

    # -- processing -------------------------------------------------------
    def start(self, dry_run):
        in_dir = self.in_var.get().strip()
        if not os.path.isdir(in_dir):
            messagebox.showerror("WAV Scene Fixer", "Please choose a valid input folder.")
            return
        out_dir = self.out_var.get().strip() or os.path.join(in_dir, "cleaned")
        if os.path.abspath(out_dir) == os.path.abspath(in_dir):
            messagebox.showerror("WAV Scene Fixer",
                                 "Output folder must differ from the input folder.")
            return
        self.save_settings()
        self.preview_btn["state"] = self.run_btn["state"] = "disabled"
        self.status_var.set("Previewing…" if dry_run else "Processing…")
        self.log["state"] = "normal"
        self.log.delete("1.0", "end")
        self.log["state"] = "disabled"

        fps_sel = self.fps_var.get()
        fps_entry = wsf.FPS_TABLE.get(fps_sel) if fps_sel != FPS_CHOICES[0] else None
        args = (in_dir, out_dir, fps_entry, fps_sel, dry_run)
        self.worker = threading.Thread(target=self.process, args=args, daemon=True)
        self.worker.start()

    def process(self, in_dir, out_dir, fps_entry, fps_sel, dry_run):
        try:
            wavs = sorted(
                os.path.join(in_dir, n) for n in os.listdir(in_dir)
                if n.lower().endswith(".wav") and os.path.isfile(os.path.join(in_dir, n))
            )
            if not wavs:
                self.emit(f"No .wav files found in {in_dir}")
                return

            self.emit(f"Scanning {len(wavs)} file(s)…")
            scenes = {}
            for w in wavs:
                try:
                    scenes[w] = wsf.get_scene(w)
                except ValueError as e:
                    self.emit(f"SKIP {os.path.basename(w)}: {e}")
            mapping = {s: wsf.clean_scene_regex(s) for s in scenes.values() if s}

            if not dry_run:
                os.makedirs(out_dir, exist_ok=True)

            changed = 0
            for w in wavs:
                if w not in scenes:
                    continue
                name = os.path.basename(w)
                raw = scenes[w]
                if raw is None:
                    self.emit(f"SKIP {name}: no scene metadata found")
                    continue
                new = mapping.get(raw, raw)
                fps_note = f", fps -> {fps_sel}" if fps_entry else ""
                self.emit(f"{name}: scene {raw!r} -> {new!r}{fps_note}")
                if not dry_run:
                    wsf.write_copy(w, os.path.join(out_dir, name), new, fps_entry)
                    changed += 1

            if dry_run:
                self.emit(f"\nDry run: {len(wavs)} file(s) scanned, nothing written.")
            else:
                self.emit(f"\n{changed} file(s) written to {out_dir}")
        except Exception as e:
            self.emit(f"ERROR: {e}")
        finally:
            self.log_queue.put(None)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
