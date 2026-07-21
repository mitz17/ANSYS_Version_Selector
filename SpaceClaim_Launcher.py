#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import webview

from launcher_common import (
    WebAPI,
    resource_path,
    prepare_external_launch_env,
    fatal_error_dialog,
)

APP_TITLE = "SpaceClaim バージョン選択ツール"
CONFIG_NAME = "spaceclaim_versions.json"
DEFAULT_SCAN_ROOTS = [
    r"C:\\Program Files\\ANSYS Inc",
    r"C:\\Program Files\\Ansys Inc",
    r"C:\\ANSYS-Inc",
]
SUPPORTED_EXTS = [".scdoc", ".step", ".stp", ".iges", ".igs"]


def find_spaceclaim_exes() -> dict[str, str]:
    targets = [
        ("scdm", "SpaceClaim.exe"),
        ("scdm", "SCDM.exe"),
        ("SpaceClaim", "SpaceClaim.exe"),
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
            for sub, exe in targets:
                p = vdir / sub / exe
                if p.exists():
                    found[vdir.name] = str(p)
                    break
            if vdir.name in found:
                continue
            # Fallback: shallow search for *spaceclaim*.exe
            try:
                for p in (vdir.glob("**/*.exe")):
                    if "spaceclaim" in p.name.lower():
                        found[vdir.name] = str(p)
                        break
            except Exception:
                pass
    return found


def launch_spaceclaim(exe: str, filepath: str | None, workdir: Path) -> dict:
    cmd = [exe]
    if filepath:
        cmd.append(filepath)
    try:
        subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=prepare_external_launch_env(),
            close_fds=True,
        )
    except Exception as e:
        return {"ok": False, "error": f"SpaceClaim の起動に失敗しました:\n{e}"}
    return {"ok": True}


class SpaceClaimAPI(WebAPI):
    def launch(self, payload: dict) -> dict:
        fpath = (payload.get("file") or "").strip().strip('"')
        p = Path(fpath) if fpath else None
        if p and not p.exists():
            return {"ok": False, "error": f"ファイルが見つかりません:\n{p}"}

        ver = (payload.get("version") or "").strip()
        exe = (self.data.get("versions") or {}).get(ver)
        if not exe or not Path(exe).exists():
            return {"ok": False, "error": "選択したバージョンの実行ファイルが無効です。設定から修正してください。"}

        workdir = p.parent.resolve() if p else Path.home()
        return launch_spaceclaim(exe, str(p) if p else None, workdir)


def build_initial_versions(api: SpaceClaimAPI):
    if api.data.get("versions"):
        return
    preset = {}
    sample = r"C:\\Program Files\\ANSYS Inc\\v252\\scdm\\SpaceClaim.exe"
    if Path(sample).exists():
        preset["v252"] = sample
    preset.update(find_spaceclaim_exes())
    if preset:
        api.data["versions"] = preset
        api._persist()


def main():
    initial_file = None
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        initial_file = sys.argv[1]

    api = SpaceClaimAPI(
        config_name=CONFIG_NAME,
        app_title=APP_TITLE,
        app_kind="spaceclaim",
        find_versions_callback=find_spaceclaim_exes,
        browse_filetypes=("Executable (*.exe)", "All files (*.*)"),
        initial_file=initial_file,
        scan_confirm_message=(
            "システムをスキャンして SpaceClaim のバージョンを検索しますか？\n既存のパスが上書きされる可能性があります。"
        ),
        extra={
            "fileGroupLabel": "入力ファイル（任意）",
            "versionLabel": "SpaceClaim バージョン",
            "browseFileTypes": ["SpaceClaim files (*.scdoc;*.step;*.stp;*.iges;*.igs)", "All files (*.*)"],
            "primaryButtonLabel": "SpaceClaimを起動",
            "scanEmptyMessage": "SpaceClaim のインストールが見つかりませんでした。",
            "scanDoneMessageTemplate": "{count} 個のバージョンを検出・更新しました。",
        },
    )
    build_initial_versions(api)

    window = webview.create_window(
        APP_TITLE,
        url=str(resource_path("webui", "app.html")),
        js_api=api,
        width=760,
        height=460,
        min_size=(640, 380),
    )
    api._window = window
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        fatal_error_dialog(APP_TITLE, f"致命的なエラー:\n{e}")
