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

APP_TITLE = "Workbench バージョン選択ツール"
CONFIG_NAME = "workbench_versions.json"
DEFAULT_SCAN_ROOTS = [
    r"C:\\Program Files\\ANSYS Inc",
    r"C:\\Program Files\\Ansys Inc",
    r"C:\\ANSYS-Inc",
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


def launch_workbench(exe: str, filepath: str | None, workdir: Path) -> dict:
    cmd = [exe]
    if filepath:
        cmd.extend(["-F", filepath])
    try:
        subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=prepare_external_launch_env(),
            close_fds=True,
        )
    except Exception as e:
        return {"ok": False, "error": f"Workbench の起動に失敗しました:\n{e}"}
    return {"ok": True}


class WorkbenchAPI(WebAPI):
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
        return launch_workbench(exe, str(p) if p else None, workdir)


def build_initial_versions(api: WorkbenchAPI):
    if api.data.get("versions"):
        return
    preset = {}
    sample = r"C:\\Program Files\\ANSYS Inc\\v252\\Framework\\bin\\Win64\\RunWB2.exe"
    if Path(sample).exists():
        preset["v252"] = sample
    preset.update(find_workbench_exes())
    if preset:
        api.data["versions"] = preset
        api._persist()


def main():
    initial_file = None
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        initial_file = sys.argv[1]

    api = WorkbenchAPI(
        config_name=CONFIG_NAME,
        app_title=APP_TITLE,
        app_kind="workbench",
        find_versions_callback=find_workbench_exes,
        browse_filetypes=("Executable (*.exe)", "All files (*.*)"),
        initial_file=initial_file,
        scan_confirm_message=(
            "システムをスキャンして Workbench のバージョンを検索しますか？\n既存のパスが上書きされる可能性があります。"
        ),
        extra={
            "fileGroupLabel": "入力ファイル（任意: .wbpj）",
            "versionLabel": "Workbench バージョン",
            "browseFileTypes": ["Workbench Project (*.wbpj)", "All files (*.*)"],
            "primaryButtonLabel": "Workbenchを起動",
            "scanEmptyMessage": "Workbench のインストールが見つかりませんでした。",
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
