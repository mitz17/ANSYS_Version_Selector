#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fluent バージョン選択ツール（README_Fluent_Launcher.md に沿った実装）

- 対象拡張子: .msh, .msh.h5, .cas, .cas.h5, .dat, .dat.h5
- 製品モード: ソルバ / メッシング
- ソルバ: 2D/3D, Double Precision, 並列数の指定
- 設定: fluent.exe のパスをバージョン名と紐付けて保存（JSON）
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from launcher_common import (
    BaseSettingsDialog,
    load_config,
    save_config,
    migrate_legacy_config,
)

APP_TITLE = "Fluent バージョン選択ツール"
CONFIG_NAME = "fluent_versions.json"
DEFAULT_SCAN_ROOTS = [
    r"C:\\Program Files\\ANSYS Inc",
    r"C:\\Program Files\\Ansys Inc",
]
SUPPORTED_EXTS = [".msh", ".msh.h5", ".cas", ".cas.h5", ".dat", ".dat.h5"]
PREFERRED_LOCALE_ENV = {
    "FLUENT_LANG": "ja-JP",
    "LANG": "ja_JP.UTF-8",
    "LC_ALL": "ja_JP.UTF-8",
}


# -------------------------- ユーティリティ --------------------------


def find_fluent_exes() -> dict[str, str]:
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
            exe = vdir / "fluent" / "ntbin" / "win64" / "fluent.exe"
            if exe.exists():
                found[vdir.name] = str(exe)
    return found


# -------------------------- ジャーナル生成 --------------------------

def build_journal_for_file(filepath: Path, product: str) -> str:
    """ソルバーモード時のみジャーナルを生成。

    既定では SI への単位設定は行いません（環境差でエラーになりうるため）。
    拡張子に応じて read-mesh/case/data を実行します。
    """
    if product == "meshing":
        return "\n"  # メッシングでは自動読込しない

    p = str(filepath)
    ext = filepath.suffix.lower()
    if ext == ".h5":
        base_ext = Path(filepath.stem).suffix.lower() + ext  # .cas.h5/.dat.h5/.msh.h5
        base_root = Path(filepath.stem).stem
    else:
        base_ext = ext
        base_root = filepath.stem

    cmds: list[str] = []

    if base_ext in [".msh", ".msh.h5"]:
        cmds.append(f"/file/read-mesh \"{p}\"")
    elif base_ext in [".cas", ".cas.h5"]:
        cmds.append(f"/file/read-case \"{p}\"")
        dat_candidates = [
            filepath.with_name(f"{base_root}.dat"),
            filepath.with_name(f"{base_root}.dat.h5"),
        ]
        dat_path = next((c for c in dat_candidates if c.exists()), None)
        if dat_path:
            cmds.append(f"/file/read-data \"{str(dat_path)}\"")
    elif base_ext in [".dat", ".dat.h5"]:
        # 可能なら同名の .cas(.h5) を先に読む
        cas_candidates = [
            filepath.with_name(f"{base_root}.cas"),
            filepath.with_name(f"{base_root}.cas.h5"),
        ]
        cas_path = next((c for c in cas_candidates if c.exists()), None)
        if cas_path:
            cmds.append(f"/file/read-case \"{str(cas_path)}\"")
        cmds.append(f"/file/read-data \"{p}\"")
    else:
        cmds.append("/report/system/proc-mem")

    return "\n".join(cmds) + "\n"


def cleanup_old_journals(max_age_hours: int = 48):
    temp_dir = Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_hours * 3600
    for path in temp_dir.glob("ansys_launcher_*.jou"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except Exception:
            pass


def launch_fluent(
    fluent_exe: str,
    mode: str,
    product: str,
    journal_text: str,
    workdir: Path,
    n_procs: int,
    env_override: dict | None = None,
    use_launcher: bool = False,
):
    # README に合わせて一時ファイルにジャーナルを保存
    cleanup_old_journals()
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        prefix="ansys_launcher_",
        suffix=".jou",
        encoding="utf-8",
        newline="\n",
    ) as tf:
        tf.write(journal_text)
        journal_path = tf.name

    cmd: list[str] = [fluent_exe]

    if use_launcher:
        # Launcher を表示したい場合は、製品/モード/並列の引数を渡さない
        # （Launcher の画面から選択してもらう）
        pass
    else:
        # 直接起動
        if product == "meshing":
            cmd.append("-meshing")
            if mode:
                cmd.append(mode)  # 2d/3d を渡すとランチャーを回避できる
        else:
            if mode:
                cmd.append(mode)  # 2d/3d/dp

        if n_procs > 1:
            cmd.append("-t" + str(n_procs))

    cmd.extend(["-i", journal_path])

    # 環境変数（日本語ロケール等）を上書きして起動
    env = os.environ.copy()
    if env_override:
        env.update(env_override)

    try:
        subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=env,
            close_fds=True,
        )
    except Exception as e:
        messagebox.showerror("起動エラー", f"Fluent の起動に失敗しました:\n{e}")


# -------------------------- UI --------------------------

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        # モダン風スタイル
        try:
            style = ttk.Style(self)
            for candidate in ("vista", "xpnative", "clam"):
                if candidate in style.theme_names():
                    style.theme_use(candidate)
                    break
            base_font = ("Segoe UI", 10)
            style.configure("TLabel", font=base_font)
            style.configure("TButton", font=base_font, padding=(10, 6))
            style.configure("TEntry", padding=4)
            style.configure("TCombobox", padding=4)
            style.configure("TLabelframe", padding=10)
            style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
            # ttk のネイティブ描画に従う（色は強制しない）
        except Exception:
            pass

        self.title(APP_TITLE)
        self.geometry("820x520")
        self.minsize(720, 360)
        self.resizable(True, True)

        self.config_path = migrate_legacy_config(CONFIG_NAME)
        self.data = load_config(self.config_path)

        if not self.data.get("versions"):
            preset = {}
            sample = r"C:\\Program Files\\ANSYS Inc\\v252\\fluent\\ntbin\\win64\\fluent.exe"
            if Path(sample).exists():
                preset["v252"] = sample
            preset.update(find_fluent_exes())
            if preset:
                self.data["versions"] = preset
                save_config(self.config_path, self.data)

        pad = 10
        # 縦に収まらない場合でもスクロールできるコンテナ
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        frm = ttk.Frame(canvas, padding=pad)
        frm_id = canvas.create_window((0, 0), window=frm, anchor="nw")
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        def _on_frame_config(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # フレーム幅に合わせてキャンバス項目を広げる
            canvas_width = container.winfo_width()
            if canvas_width:
                canvas.itemconfigure(frm_id, width=canvas_width - vbar.winfo_width())

        frm.bind("<Configure>", _on_frame_config)
        self.bind("<Configure>", _on_frame_config)

        frm.grid_columnconfigure(0, weight=1)
        frm.grid_columnconfigure(1, weight=1)

        # ファイル選択
        filegrp = ttk.Labelframe(frm, text="入力ファイル（任意）")
        filegrp.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, pad))
        filegrp.grid_columnconfigure(0, weight=1)
        self.file_var = tk.StringVar()
        ent_file = ttk.Entry(filegrp, textvariable=self.file_var)
        ent_file.grid(row=0, column=0, sticky="ew")
        ttk.Button(filegrp, text="参照...", command=self.browse_file).grid(row=0, column=1, padx=(8, 0))

        # バージョン選択（ワンクリック選択：Listbox）
        vergrp = ttk.Labelframe(frm, text="Fluent バージョン")
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

        # 製品モード
        self.product_var = tk.StringVar(value="solver")
        prodgrp = ttk.Labelframe(frm, text="製品モード")
        prodgrp.grid(row=1, column=1, sticky="w", padx=(pad, 0), pady=(0, pad))
        ttk.Radiobutton(prodgrp, text="ソルバ", variable=self.product_var, value="solver").grid(row=0, column=0, padx=(2,6))
        ttk.Radiobutton(prodgrp, text="メッシング", variable=self.product_var, value="meshing").grid(row=0, column=1, padx=(2,0))

        # 言語選択は不要（直接起動を想定）

        # 次元・精度（ソルバのみ）
        self.dim_var = tk.StringVar(value="3d")
        self.dp_var = tk.BooleanVar(value=True)
        dimgrp = ttk.Labelframe(frm, text="次元・精度（ソルバ）")
        dimgrp.grid(row=2, column=0, columnspan=2, pady=(0, pad), sticky="w")
        ttk.Radiobutton(dimgrp, text="2D", variable=self.dim_var, value="2d").grid(row=0, column=0, padx=(2,6))
        ttk.Radiobutton(dimgrp, text="3D", variable=self.dim_var, value="3d").grid(row=0, column=1, padx=(2,6))
        ttk.Checkbutton(dimgrp, text="Double Precision", variable=self.dp_var).grid(row=0, column=2, padx=(10, 0))

        # 並列（1クリックで切替できるラジオボタン群）
        self.proc_var = tk.StringVar(value="4")
        procgrp = ttk.Labelframe(frm, text="並列プロセス数")
        procgrp.grid(row=2, column=2, pady=(0, pad), sticky="w")
        procs = ("1", "4", "12", "15", "20", "24")
        for idx, val in enumerate(procs):
            ttk.Radiobutton(procgrp, text=val, value=val, variable=self.proc_var).grid(row=0, column=idx, padx=(2, 2))

        # 実行
        action_frm = ttk.Frame(frm)
        action_frm.grid(row=3, column=0, columnspan=2, pady=(pad, 0), sticky="w")
        ttk.Button(action_frm, text="Fluent Launcherを起動", command=self.run_launcher).pack(anchor="w")
        ttk.Button(action_frm, text="Fluentを起動", command=self.run_direct).pack(anchor="w", pady=(8, 0))

        # ヒント
        self.help_txt = (
            "ヒント\n"
            "・このツールを .msh/.cas/.dat(.h5) の既定アプリに設定すると、ダブルクリックで本ツールが開き、\n"
            "  バージョン選択後に Fluent が起動します。\n"
            "・.dat のみを開く場合、対応する .cas が必要になることがあります。\n"
            "・ソルバの場合はジャーナルで自動的にファイル読込を行います。"
        )
        ttk.Button(frm, text="ヘルプ", command=self.show_help).grid(row=4, column=0, sticky="w", pady=(pad//2, 0))

        # 引数でファイルが渡された場合にセット
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if Path(arg).exists():
                self.file_var.set(arg)

    def refresh_versions(self):
        versions = list((self.data.get("versions") or {}).keys())
        self.lst_ver.delete(0, tk.END)
        for v in versions:
            self.lst_ver.insert(tk.END, v)
        if versions:
            # 先頭を選択状態に
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

    def on_version_select(self, _event):
        sel = self.lst_ver.curselection()
        if sel:
            self.ver_var.set(self.lst_ver.get(sel[0]))

    def show_help(self):
        try:
            messagebox.showinfo("ヒント", self.help_txt, parent=self)
        except Exception:
            messagebox.showinfo("ヒント", "このツールを既定アプリに設定してダブルクリック起動すると便利です。\n.dat は .cas と対で扱う場合があります。", parent=self)

    def browse_file(self):
        f = filedialog.askopenfilename(
            title="Fluent 対応ファイルを選択",
            filetypes=[
                ("Fluent files", ["*.msh", "*.msh.h5", "*.cas", "*.cas.h5", "*.dat", "*.dat.h5"]),
                ("All files", "*.*"),
            ],
        )
        if f:
            self.file_var.set(f)

    def resolve_mode(self) -> str:
        # メッシング時も 2D/3D を渡すと Launcher を回避できる
        if self.product_var.get() == "meshing":
            return "3d"
        dim = self.dim_var.get()
        dp = self.dp_var.get()
        mode = dim
        if dp:
            mode += "dp"
        return mode

    def _run(self, use_launcher: bool):
        fpath = self.file_var.get().strip().strip('"')
        journal = "\n"
        workdir = Path.home()

        if fpath:
            p = Path(fpath)
            if not p.exists():
                messagebox.showerror("エラー", f"ファイルが見つかりません:\n{p}")
                return
            product_for_journal = self.product_var.get()
            journal = build_journal_for_file(p, product_for_journal)
            workdir = p.parent.resolve()

        ver = self.ver_var.get().strip()
        exe = (self.data.get("versions") or {}).get(ver)
        if not exe or not Path(exe).exists():
            messagebox.showerror("エラー", "選択したバージョンの fluent.exe が無効です。設定から修正してください。")
            return

        product = self.product_var.get()
        mode = self.resolve_mode()

        n_procs = 1
        try:
            n_procs = int(self.proc_var.get())
            if n_procs < 1:
                n_procs = 1
        except (ValueError, TypeError):
            pass

        # Prefer Japanese locale when possible without overriding user settings
        env_override = {k: v for k, v in PREFERRED_LOCALE_ENV.items() if not os.environ.get(k)}
        if not env_override:
            env_override = None

        launch_fluent(exe, mode, product, journal, workdir, n_procs, env_override, use_launcher)
        self.destroy()

    def run_launcher(self):
        self._run(use_launcher=True)

    def run_direct(self):
        self._run(use_launcher=False)


class SettingsDialog(BaseSettingsDialog):
    def __init__(self, parent, data: dict):
        super().__init__(
            parent,
            data,
            window_title="バージョン設定",
            executable_label="fluent.exe のパス:",
            browse_title="fluent.exe を選択",
            browse_filetypes=[("Executable", "fluent.exe"), ("All files", "*.*")],
            scan_confirm_message="システムをスキャンして Fluent のバージョンを検索しますか？\n既存のパスが上書きされる可能性があります。",
            scan_empty_message="Fluent のインストールが見つかりませんでした。",
            scan_done_message="{count} 個のバージョンを検出・更新しました。",
            find_versions_callback=find_fluent_exes,
        )


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        messagebox.showerror(APP_TITLE, f"致命的なエラー:\n{e}")
