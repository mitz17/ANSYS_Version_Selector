#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fluent バージョン選択ツール

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

import webview

from launcher_common import (
    WebAPI,
    resource_path,
    prepare_external_launch_env,
    fatal_error_dialog,
)

APP_TITLE = "Fluent バージョン選択ツール"
CONFIG_NAME = "fluent_versions.json"
DEFAULT_SCAN_ROOTS = [
    r"C:\\Program Files\\ANSYS Inc",
    r"C:\\Program Files\\Ansys Inc",
    r"C:\\ANSYS-Inc",
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


def resolve_mode(product: str, dim: str, dp: bool) -> str:
    # メッシング時も 2D/3D を渡すと Launcher を回避できる
    if product == "meshing":
        return "3d"
    mode = dim or "3d"
    if dp:
        mode += "dp"
    return mode


def launch_fluent(
    fluent_exe: str,
    mode: str,
    product: str,
    journal_text: str,
    workdir: Path,
    n_procs: int,
    env_override: dict | None = None,
    use_launcher: bool = False,
) -> dict:
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
    env = prepare_external_launch_env(env_override)

    try:
        subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=env,
            close_fds=True,
        )
    except Exception as e:
        return {"ok": False, "error": f"Fluent の起動に失敗しました:\n{e}"}
    return {"ok": True}


# -------------------------- JS-API --------------------------

class FluentAPI(WebAPI):
    def launch(self, payload: dict) -> dict:
        fpath = (payload.get("file") or "").strip().strip('"')
        journal = "\n"
        workdir = Path.home()

        if fpath:
            p = Path(fpath)
            if not p.exists():
                return {"ok": False, "error": f"ファイルが見つかりません:\n{p}"}
            product_for_journal = payload.get("product", "solver")
            journal = build_journal_for_file(p, product_for_journal)
            workdir = p.parent.resolve()

        ver = (payload.get("version") or "").strip()
        exe = (self.data.get("versions") or {}).get(ver)
        if not exe or not Path(exe).exists():
            return {"ok": False, "error": "選択したバージョンの fluent.exe が無効です。設定から修正してください。"}

        product = payload.get("product", "solver")
        mode = resolve_mode(product, payload.get("dim", "3d"), bool(payload.get("dp", True)))

        try:
            n_procs = int(payload.get("procs") or 1)
        except (ValueError, TypeError):
            n_procs = 1
        n_procs = max(1, n_procs)

        # Prefer Japanese locale when possible without overriding user settings
        env_override = {k: v for k, v in PREFERRED_LOCALE_ENV.items() if not os.environ.get(k)}
        if not env_override:
            env_override = None

        return launch_fluent(
            exe, mode, product, journal, workdir, n_procs, env_override,
            bool(payload.get("useLauncher", False)),
        )


def build_initial_versions(api: FluentAPI):
    if api.data.get("versions"):
        return
    preset = {}
    sample = r"C:\\Program Files\\ANSYS Inc\\v252\\fluent\\ntbin\\win64\\fluent.exe"
    if Path(sample).exists():
        preset["v252"] = sample
    preset.update(find_fluent_exes())
    if preset:
        api.data["versions"] = preset
        api._persist()


def main():
    initial_file = None
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        initial_file = sys.argv[1]

    api = FluentAPI(
        config_name=CONFIG_NAME,
        app_title=APP_TITLE,
        app_kind="fluent",
        find_versions_callback=find_fluent_exes,
        browse_filetypes=("Executable (fluent.exe)", "All files (*.*)"),
        initial_file=initial_file,
        scan_confirm_message=(
            "システムをスキャンして Fluent のバージョンを検索しますか？\n既存のパスが上書きされる可能性があります。"
        ),
        extra={
            "fileGroupLabel": "入力ファイル（任意）",
            "versionLabel": "Fluent バージョン",
            "browseFileTypes": ["Fluent files (*.msh;*.msh.h5;*.cas;*.cas.h5;*.dat;*.dat.h5)", "All files (*.*)"],
            "primaryButtonLabel": "Fluentを起動",
            "showLauncherButton": True,
            "launcherButtonLabel": "Fluent Launcherを起動",
            "scanEmptyMessage": "Fluent のインストールが見つかりませんでした。",
            "scanDoneMessageTemplate": "{count} 個のバージョンを検出・更新しました。",
            "helpText": (
                "・このツールを .msh/.cas/.dat(.h5) の既定アプリに設定すると、ダブルクリックで本ツールが開き、\n"
                "  バージョン選択後に Fluent が起動します。\n"
                "・.dat のみを開く場合、対応する .cas が必要になることがあります。\n"
                "・ソルバの場合はジャーナルで自動的にファイル読込を行います。"
            ),
        },
    )
    build_initial_versions(api)

    window = webview.create_window(
        APP_TITLE,
        url=str(resource_path("webui", "app.html")),
        js_api=api,
        width=880,
        height=640,
        min_size=(720, 480),
    )
    api._window = window
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        fatal_error_dialog(APP_TITLE, f"致命的なエラー:\n{e}")
