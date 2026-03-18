from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "executable"):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_base_dir() -> Path:
    base = app_base_dir()
    if not getattr(sys, "frozen", False):
        return base

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = Path(appdata) / "AnsysLaunchers"
    else:
        candidate = Path.home() / ".ansys_launchers"

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except Exception:
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return base


def load_config(cfg_path: Path) -> dict:
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"versions": {}}


def save_config(cfg_path: Path, data: dict):
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def migrate_legacy_config(config_name: str) -> Path:
    legacy_config = app_base_dir() / config_name
    config_path = config_base_dir() / config_name
    if not config_path.exists() and legacy_config.exists():
        try:
            shutil.copy2(legacy_config, config_path)
        except Exception:
            pass
    return config_path


class BaseSettingsDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        data: dict,
        window_title: str,
        executable_label: str,
        browse_title: str,
        browse_filetypes,
        scan_confirm_message: str,
        scan_empty_message: str,
        scan_done_message: str,
        find_versions_callback,
        initialdir: str = r"C:\\Program Files\\ANSYS Inc",
    ):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title(window_title)
        self.parent = parent
        self.data = {"versions": dict((data or {}).get("versions", {}))}
        self.result = False
        self.browse_title = browse_title
        self.browse_filetypes = browse_filetypes
        self.scan_confirm_message = scan_confirm_message
        self.scan_empty_message = scan_empty_message
        self.scan_done_message = scan_done_message
        self.find_versions_callback = find_versions_callback
        self.initialdir = initialdir

        pad = 10
        frm = ttk.Frame(self, padding=pad)
        frm.pack(fill="both", expand=True)
        self.geometry("640x480")

        cols = ("Version", "Path")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", height=8)
        self.tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
        frm.grid_rowconfigure(0, weight=1)
        frm.grid_columnconfigure(1, weight=1)

        vsb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=3, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("Version", width=100, anchor="w")
        self.tree.column("Path", width=400, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        self.ver_var = tk.StringVar()
        self.path_var = tk.StringVar()
        ttk.Label(frm, text="バージョン名").grid(row=1, column=0, sticky="w", pady=(pad, 0))
        ttk.Entry(frm, textvariable=self.ver_var, width=20).grid(row=2, column=0, sticky="w")
        ttk.Label(frm, text=executable_label).grid(row=1, column=1, sticky="w", pady=(pad, 0), padx=(pad, 0))
        ttk.Entry(frm, textvariable=self.path_var, width=60).grid(row=2, column=1, sticky="we", padx=(pad, 0))
        ttk.Button(frm, text="...", command=self.browse_exe, width=3).grid(row=2, column=2, sticky="w", padx=(5, 0))

        btn_frm = ttk.Frame(frm, padding=(0, pad, 0, 0))
        btn_frm.grid(row=3, column=0, columnspan=3, sticky="ew")
        ttk.Button(btn_frm, text="追加/更新", command=self.add_update).pack(side="left")
        ttk.Button(btn_frm, text="削除", command=self.delete_item).pack(side="left", padx=(5, 0))
        ttk.Button(btn_frm, text="上へ", command=lambda: self.move_item(-1)).pack(side="left", padx=(5, 0))
        ttk.Button(btn_frm, text="下へ", command=lambda: self.move_item(1)).pack(side="left", padx=(5, 0))
        ttk.Button(btn_frm, text="スキャン", command=self.scan_versions).pack(side="left", padx=(20, 0))
        right_btn_frm = ttk.Frame(btn_frm)
        right_btn_frm.pack(side="right")
        ttk.Button(right_btn_frm, text="保存して閉じる", command=self.save_and_close).pack(side="left")
        ttk.Button(right_btn_frm, text="キャンセル", command=self.cancel).pack(side="left", padx=(5, 0))

        self.load_versions()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.wait_window(self)

    def load_versions(self):
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        for ver, path in self.data.get("versions", {}).items():
            self.tree.insert("", "end", values=(ver, path))

    def on_select(self, _event):
        selected = self.tree.selection()
        if not selected:
            return
        item = self.tree.item(selected[0])
        ver, path = item["values"]
        self.ver_var.set(ver)
        self.path_var.set(path)

    def browse_exe(self):
        f = filedialog.askopenfilename(
            title=self.browse_title,
            filetypes=self.browse_filetypes,
            initialdir=self.initialdir,
        )
        if f:
            self.path_var.set(f)

    def add_update(self):
        ver = self.ver_var.get().strip()
        path = self.path_var.get().strip()
        if not ver or not path:
            messagebox.showwarning("入力エラー", "バージョン名とパスを入力してください。", parent=self)
            return
        if "versions" not in self.data:
            self.data["versions"] = {}
        self.data["versions"][ver] = path
        self.load_versions()
        self.clear_entries()

    def delete_item(self):
        ver = self.ver_var.get().strip()
        if not ver:
            selected = self.tree.selection()
            if selected:
                item = self.tree.item(selected[0])
                ver = item["values"][0]
            else:
                messagebox.showwarning("選択エラー", "削除するバージョンを選択または入力してください。", parent=self)
                return
        if "versions" in self.data and ver in self.data["versions"]:
            if messagebox.askyesno("確認", f"バージョン '{ver}' を削除しますか？", parent=self):
                del self.data["versions"][ver]
                self.load_versions()
                self.clear_entries()

    def move_item(self, direction: int):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("選択エラー", "並べ替えるバージョンを選択してください。", parent=self)
            return

        ver = self.tree.item(selected[0])["values"][0]
        versions = list((self.data.get("versions") or {}).items())
        index = next((i for i, (name, _) in enumerate(versions) if name == ver), None)
        if index is None:
            return

        new_index = index + direction
        if new_index < 0 or new_index >= len(versions):
            return

        versions[index], versions[new_index] = versions[new_index], versions[index]
        self.data["versions"] = dict(versions)
        self.load_versions()

        children = self.tree.get_children()
        target = children[new_index]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self.on_select(None)

    def scan_versions(self):
        if not messagebox.askyesno("確認", self.scan_confirm_message, parent=self):
            return
        found = self.find_versions_callback()
        if not found:
            messagebox.showinfo("スキャン結果", self.scan_empty_message, parent=self)
            return
        if "versions" not in self.data:
            self.data["versions"] = {}
        self.data["versions"].update(found)
        self.load_versions()
        messagebox.showinfo("完了", self.scan_done_message.format(count=len(found)), parent=self)

    def clear_entries(self):
        self.ver_var.set("")
        self.path_var.set("")
        if self.tree.selection():
            self.tree.selection_remove(self.tree.selection()[0])

    def save_and_close(self):
        self.result = True
        self.destroy()

    def cancel(self):
        self.result = False
        self.destroy()
