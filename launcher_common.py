from __future__ import annotations

import json
import os
import shutil
import sys
import ctypes
import threading
import time
from pathlib import Path

import webview


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "executable"):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """PyInstaller onefile展開先も考慮したリソース(webui資産等)の解決。"""
    base = Path(getattr(sys, "_MEIPASS", None) or app_base_dir())
    return base.joinpath(*parts)


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


def prepare_external_launch_env(env_override: dict | None = None) -> dict:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)

    # PyInstaller onefile 実行時は DLL 検索先や一時展開ディレクトリ情報が
    # 外部プロセスへ引き継がれて、終了時の _MEI 削除失敗につながることがある。
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    for key in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE"):
        env.pop(key, None)

    return env


def fatal_error_dialog(title: str, message: str):
    """webview/tkinterのどちらも使えない致命的エラー時の最終手段。"""
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
        except Exception:
            pass
    print(f"{title}: {message}", file=sys.stderr)


class WebAPI:
    """3つのランチャー共通のJS-API(pywebview)基底クラス。

    設定ファイルの読み書き・バージョン一覧の追加/削除/並べ替え/スキャン・
    ネイティブファイルダイアログなど、UI非依存のロジックをまとめる。
    """

    def __init__(
        self,
        config_name: str,
        app_title: str,
        app_kind: str,
        find_versions_callback,
        browse_filetypes: tuple[str, ...],
        initial_file: str | None = None,
        scan_confirm_message: str = "",
        extra: dict | None = None,
    ):
        self.config_path = migrate_legacy_config(config_name)
        self.data = load_config(self.config_path)
        self.app_title = app_title
        self.app_kind = app_kind
        self.find_versions_callback = find_versions_callback
        self.browse_filetypes = browse_filetypes
        self.initial_file = initial_file
        self.scan_confirm_message = scan_confirm_message
        self.extra = extra or {}
        # 注意: 属性名は必ずアンダースコア始まりにすること。
        # pywebview は js_api オブジェクトを dir() で再帰的に走査して JS へ自動公開するが、
        # `_` 始まりの属性は走査対象から除外される。ここに Window の参照をアンダースコア無しの
        # 属性として持たせると、pywebview が window.native (.NET のネイティブウィンドウ) まで
        # 再帰的に辿ろうとして COM のクロススレッドアクセス例外や無限再帰
        # (AccessibilityObject.Bounds.Empty.Empty... 等) を引き起こす。
        self._window = None  # create_window() 後に呼び出し側が設定する

    # ---- bootstrap ----
    def get_bootstrap(self):
        return {
            "title": self.app_title,
            "appKind": self.app_kind,
            "versions": self.data.get("versions", {}),
            "initialFile": self.initial_file,
            "scanConfirmMessage": self.scan_confirm_message,
            "extra": self.extra,
        }

    def _persist(self):
        save_config(self.config_path, self.data)

    # ---- バージョン管理 ----
    def add_or_update_version(self, name: str, path: str):
        name = (name or "").strip()
        path = (path or "").strip()
        if not name or not path:
            return {"ok": False, "error": "バージョン名とパスを入力してください。"}
        self.data.setdefault("versions", {})[name] = path
        self._persist()
        return {"ok": True, "versions": self.data["versions"]}

    def delete_version(self, name: str):
        versions = self.data.get("versions", {})
        if name in versions:
            del versions[name]
            self._persist()
        return {"ok": True, "versions": self.data.get("versions", {})}

    def move_version(self, name: str, direction: int):
        versions = list((self.data.get("versions") or {}).items())
        idx = next((i for i, (n, _) in enumerate(versions) if n == name), None)
        if idx is None:
            return {"ok": False, "versions": dict(versions)}
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(versions):
            return {"ok": False, "versions": dict(versions)}
        versions[idx], versions[new_idx] = versions[new_idx], versions[idx]
        self.data["versions"] = dict(versions)
        self._persist()
        return {"ok": True, "versions": self.data["versions"]}

    def scan_versions(self):
        found = self.find_versions_callback()
        if not found:
            return {"ok": True, "count": 0, "versions": self.data.get("versions", {})}
        self.data.setdefault("versions", {}).update(found)
        self._persist()
        return {"ok": True, "count": len(found), "versions": self.data["versions"]}

    # ---- ネイティブダイアログ ----
    def browse_exe(self):
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            directory=r"C:\\Program Files\\ANSYS Inc",
            file_types=self.browse_filetypes,
        )
        return result[0] if result else None

    def browse_input_file(self, file_types: list[str]):
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=tuple(file_types),
        )
        return result[0] if result else None

    def close(self):
        # JS ブリッジ呼び出しの戻り値マーシャリング中に window.destroy() を同期実行すると、
        # 破棄途中のネイティブウィンドウを pywebview 側が辿ろうとして
        # RecursionError (AccessibilityObject.Bounds.Empty...) を起こすことがある。
        # この呼び出しの完了後にウィンドウを破棄するよう、別スレッドへ逃がす。
        if self._window:
            window = self._window
            def _destroy_later():
                time.sleep(0.15)
                try:
                    window.destroy()
                except Exception:
                    pass
            threading.Thread(target=_destroy_later, daemon=True).start()
        return {"ok": True}
