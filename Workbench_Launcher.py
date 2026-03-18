#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from launcher_common import (
    BaseSettingsDialog,
    load_config,
    save_config,
    migrate_legacy_config,
)

APP_TITLE = "Workbench バージョン選択ツール"
CONFIG_NAME = "workbench_versions.json"
DEFAULT_SCAN_ROOTS = [
    r"C:\\Program Files\\ANSYS Inc",
    r"C:\\Program Files\\Ansys Inc",
]
SUPPORTED_EXTS = [".wbpj"]


def find_workbench_exes() -> dict[str, str]:
    candidates = [
        ("Framework\\bin\\Win64", "RunWB2.exe"),
        ("Framework\\bin\\Win64", "ansyswb.exe"),
    ]
    found: dict[str, str] = {}
    for root in DEFAULT_SCAN_ROOTS:
        base = Path(root)
        if not base.exists():
            continue
        for vdir in base.iterdir():
            if not vdir.is_dir():
                continue
            name = vdir.name.lower()
            if not name.startswith("v"):
                continue
            for sub, exe in candidates:
                p = vdir / sub / exe
                if p.exists():
                    found[vdir.name] = str(p)
                    break
            if vdir.name in found:
                continue
            # Fallback search for *wb*.exe under Framework/bin/Win64
            try:
                fb = vdir / "Framework" / "bin" / "Win64"
                if fb.exists():
                    for p in fb.glob("*.exe"):
                        if "wb" in p.stem.lower():
                            found[vdir.name] = str(p)
                            break
            except Exception:
                pass
    return found


def launch_workbench(exe: str, filepath: str | None, workdir: Path):
    cmd = [exe]
    if filepath:
        cmd.extend(["-F", filepath])  # ← 修正
    try:
        subprocess.Popen(
            cmd,
            cwd=str(workdir),
            close_fds=True,
        )
    except Exception as e:
        messagebox.showerror("起動エラー", f"Workbench の起動に失敗しました:\n{e}")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        try:
            style = ttk.Style(self)
            for candidate in ("vista", "xpnative", "clam"):
                if candidate in style.theme_names():
                    style.theme_use(candidate)
                    break
            base_font = ("Segoe UI", 10)
            style.configure("TLabel", font=base_font)
            style.configure("TButton", font=base_font, padding=(10, 6))
            style.configure("TLabelframe", padding=10)
            style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
            # 既定色のまま（可読性重視）
        except Exception:
            pass

        self.title(APP_TITLE)
        self.geometry("820x360")
        self.minsize(680, 320)
        self.resizable(True, True)

        self.config_path = migrate_legacy_config(CONFIG_NAME)
        self.data = load_config(self.config_path)
        if not self.data.get("versions"):
            preset = {}
            sample = r"C:\\Program Files\\ANSYS Inc\\v252\\Framework\\bin\\Win64\\RunWB2.exe"
            if Path(sample).exists():
                preset["v252"] = sample
            preset.update(find_workbench_exes())
            if preset:
                self.data["versions"] = preset
                save_config(self.config_path, self.data)

        pad = 12
        frm = ttk.Frame(self, padding=pad)
        frm.pack(fill="both", expand=True)
        frm.grid_columnconfigure(0, weight=1)
        frm.grid_columnconfigure(1, weight=1)

        # ファイル
        filegrp = ttk.Labelframe(frm, text="入力ファイル（任意: .wbpj）")
        filegrp.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, pad))
        filegrp.grid_columnconfigure(0, weight=1)
        self.file_var = tk.StringVar()
        ttk.Entry(filegrp, textvariable=self.file_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(filegrp, text="参照...", command=self.browse_file).grid(row=0, column=1, padx=(8, 0))

        # バージョン（ワンクリック）
        vergrp = ttk.Labelframe(frm, text="Workbench バージョン")
        vergrp.grid(row=1, column=0, sticky="nsew", pady=(0, pad))
        vergrp.grid_rowconfigure(0, weight=1)
        vergrp.grid_columnconfigure(0, weight=1)
        self.ver_var = tk.StringVar()
        self.lst_ver = tk.Listbox(vergrp, height=6)
        self.lst_ver.grid(row=0, column=0, sticky="nsew")
        vsb_ver = ttk.Scrollbar(vergrp, orient="vertical", command=self.lst_ver.yview)
        vsb_ver.grid(row=0, column=1, sticky="ns")
        self.lst_ver.configure(yscrollcommand=vsb_ver.set)
        self.lst_ver.bind("<<ListboxSelect>>", self.on_version_select)
        ttk.Button(vergrp, text="設定...", command=self.open_settings).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.refresh_versions()

        # 実行
        ttk.Button(frm, text="Workbench を起動", command=self.run).grid(
            row=2, column=0, pady=(pad, 0), sticky="w"
        )

        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if Path(arg).exists():
                self.file_var.set(arg)

    def browse_file(self):
        f = filedialog.askopenfilename(
            title="Workbench プロジェクトを選択",
            filetypes=[("Workbench Project", "*.wbpj"), ("All files", "*.*")],
        )
        if f:
            self.file_var.set(f)

    def refresh_versions(self):
        versions = list((self.data.get("versions") or {}).keys())
        self.lst_ver.delete(0, tk.END)
        for v in versions:
            self.lst_ver.insert(tk.END, v)
        if versions:
            self.lst_ver.selection_clear(0, tk.END)
            self.lst_ver.selection_set(0)
            self.lst_ver.activate(0)
            self.ver_var.set(versions[0])

    def open_settings(self):
        dialog = SettingsDialog(self, self.data)
        if dialog.result:
            self.data = dialog.data
            save_config(self.config_path, self.data)
            self.refresh_versions()

    def on_version_select(self, _):
        sel = self.lst_ver.curselection()
        if sel:
            self.ver_var.set(self.lst_ver.get(sel[0]))

    def run(self):
        fpath = self.file_var.get().strip().strip('"')
        p = Path(fpath) if fpath else None
        if p and not p.exists():
            messagebox.showerror("エラー", f"ファイルが見つかりません:\n{p}")
            return
        ver = self.ver_var.get().strip()
        exe = (self.data.get("versions") or {}).get(ver)
        if not exe or not Path(exe).exists():
            messagebox.showerror("エラー", "選択したバージョンの実行ファイルが無効です。設定から修正してください。")
            return
        workdir = p.parent.resolve() if p else Path.home()
        launch_workbench(exe, str(p) if p else None, workdir)
        self.destroy()


class SettingsDialog(BaseSettingsDialog):
    def __init__(self, parent, data: dict):
        super().__init__(
            parent,
            data,
            window_title="バージョン設定",
            executable_label="実行ファイルのパス:",
            browse_title="実行ファイルを選択",
            browse_filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            scan_confirm_message="システムをスキャンして Workbench のバージョンを検索しますか？\n既存のパスが上書きされる可能性があります。",
            scan_empty_message="Workbench のインストールが見つかりませんでした。",
            scan_done_message="{count} 個のバージョンを検出・更新しました。",
            find_versions_callback=find_workbench_exes,
        )


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        messagebox.showerror(APP_TITLE, f"致命的なエラー:\n{e}")
