#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fluent バージョン選択ツール

- 対象拡張子: .msh, .msh.h5, .cas, .cas.h5, .dat, .dat.h5
- 製品モード: ソルバ / メッシング
- ソルバ: 2D/3D, Double Precision, 並列数の指定
- 起動設定: 日本語起動 (lang=ja), CPU / Native GPU Solver, GPU Remapping, GPU Hybrid Precision
- 設定: fluent.exe のパスをバージョン名と紐付けて保存（JSON）
- デフォルト設定: 上記の起動設定を同じ JSON の "defaults" に保存し、次回起動時に復元
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PureWindowsPath

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

# 日本語 GUI で起動するときに Fluent プロセスへ渡す環境変数。
# 以前は PREFERRED_LOCALE_ENV (FLUENT_LANG / LANG / LC_ALL) を「未設定なら常に」適用していたが、
# 「日本語で起動」チェックボックスの ON/OFF を確実に反映させるため、ON のときだけ適用する方式に変更した。
# Windows の環境変数名は大文字・小文字を区別しないため、適用時は既存の LANG / Lang 等を置き換える。
JAPANESE_LANG_ENV = {"lang": "ja"}

# Fluent Launcher 向けの起動オプションを渡す環境変数（ユーザー指定）
LAUNCHER_OPTIONS_ENV = "FLUENT_LAUNCHER_OPTIONS"
GPU_ARG = "-gpu"
GPU_REMAP_ARG = "-gpu_remap"
GPU_HYBRID_PRECISION_ARG = "-gpu_hybrid_precision"

# 各機能が使える最小リリース（3 桁の Ansys リリース番号: 251 = 2025 R1）
#  - Native GPU Solver (-gpu)             : 2023 R1 以降
#  - CPU/GPU Remapping (-gpu_remap)       : 2025 R1 マニュアルで記載あり（2024 R2 には記載なし）
#  - Hybrid Precision (-gpu_hybrid_precision): 2026 R1 で β 機能として追加（3ddp と併用）
GPU_MIN_RELEASE = 231
GPU_REMAP_MIN_RELEASE = 251
GPU_HYBRID_MIN_RELEASE = 261

# デフォルト設定（Python / JavaScript で同じキー名を使う）
FACTORY_DEFAULTS = {
    "version": "",
    "product": "solver",            # solver / meshing
    "dim": "3d",                    # 2d / 3d
    "dp": True,                     # Double Precision
    "procs": "4",                   # 並列プロセス数
    "japanese": False,              # 日本語で起動
    "solverType": "cpu",            # cpu / gpu (Native GPU Solver)
    "gpuRemap": True,               # GPU Remapping
    "gpuHybridPrecision": True,     # GPU Hybrid Precision
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


def detect_fluent_release(version_name: str = "", exe_path: str = "") -> int | None:
    """バージョン名や fluent.exe のパスから 3 桁のリリース番号 (例: 252) を推定する。

    パス中の ...\\v252\\fluent\\... を優先し、見つからなければバージョン名 (v252 等) を見る。
    判定できない場合は None。
    """
    for part in reversed(PureWindowsPath(exe_path or "").parts):
        m = re.fullmatch(r"v(\d{3})", part.strip().lower())
        if m:
            return int(m.group(1))
    name = (version_name or "").strip().lower()
    m = re.fullmatch(r"v?(\d{3})", name) or re.search(r"(?<![0-9a-z])v(\d{3})(?![0-9])", name)
    if m:
        return int(m.group(1))
    return None


def format_release(release: int) -> str:
    return f"{2000 + release // 10} R{release % 10}"


def to_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("1", "true", "yes", "on"):
            return True
        if v in ("0", "false", "no", "off", ""):
            return False
    return default


def normalize_fluent_settings(raw, versions: dict | None = None) -> dict:
    """保存値・UI からの値を検証し、不足や不正値を既定値で補う。

    versions を渡した場合、保存済みバージョンが存在しなければ先頭の利用可能バージョンへ
    フォールバックする（登録が無ければ空文字）。
    """
    src = raw if isinstance(raw, dict) else {}
    out = dict(FACTORY_DEFAULTS)

    version = src.get("version")
    out["version"] = version.strip() if isinstance(version, str) else ""
    if versions is not None:
        names = list(versions.keys())
        if out["version"] not in versions:
            out["version"] = names[0] if names else ""

    product = src.get("product")
    out["product"] = product if product in ("solver", "meshing") else FACTORY_DEFAULTS["product"]

    dim = src.get("dim")
    out["dim"] = dim if dim in ("2d", "3d") else FACTORY_DEFAULTS["dim"]

    procs = src.get("procs")
    try:
        procs_int = int(str(procs).strip())
    except (TypeError, ValueError):
        procs_int = 0
    out["procs"] = str(procs_int) if procs_int >= 1 else FACTORY_DEFAULTS["procs"]

    solver_type = src.get("solverType")
    out["solverType"] = solver_type if solver_type in ("cpu", "gpu") else FACTORY_DEFAULTS["solverType"]

    for key in ("dp", "japanese", "gpuRemap", "gpuHybridPrecision"):
        out[key] = to_bool(src.get(key), FACTORY_DEFAULTS[key])
    return out


def apply_env_overrides(env: dict, overrides: dict | None) -> dict:
    """環境変数を大文字・小文字を区別せずに上書きする（Windows の仕様に合わせる）。

    値が None のキーは削除する。os.environ.copy() は Windows では大文字キーになるため、
    単純な dict.update() だと "LANG" と "lang" が重複して両方渡ってしまう問題を防ぐ。
    """
    result = dict(env)
    for key, value in (overrides or {}).items():
        for existing in [k for k in result if k.upper() == key.upper()]:
            del result[existing]
        if value is not None:
            result[key] = str(value)
    return result


def get_env_ci(env: dict, name: str) -> str | None:
    for k, v in env.items():
        if k.upper() == name.upper():
            return v
    return None


def merge_launcher_options(existing: str | None, add_tokens: list[str], strip_all_gpu: bool) -> str:
    """FLUENT_LAUNCHER_OPTIONS の既存値を維持しつつ、GPU 関連トークンを入れ替える。

    - 本ツールが管理するトークン (-gpu, -gpu_remap, -gpu_hybrid_precision) は一旦除去してから
      必要なものだけ追加する（重複防止）。
    - strip_all_gpu=True (CPU Solver / メッシング) のときは -gpu=1,2 等も含めて GPU 系を全て除去する。
    - それ以外の起動オプションは順序を保って残す。
    """
    managed = {GPU_ARG, GPU_REMAP_ARG, GPU_HYBRID_PRECISION_ARG}
    tokens: list[str] = []
    for tok in (existing or "").split():
        low = tok.lower()
        if low in managed:
            continue
        if strip_all_gpu and low.startswith("-gpu"):
            continue
        if tok not in tokens:
            tokens.append(tok)
    for tok in add_tokens:
        if tok not in tokens:
            tokens.append(tok)
    return " ".join(tokens)


def build_launch_options(
    product: str,
    dim: str,
    solver_type: str,
    gpu_remap: bool,
    gpu_hybrid: bool,
    dp: bool,
    release: int | None,
    version_label: str = "",
    use_launcher: bool = False,
) -> tuple[list[str] | None, str | None]:
    """GPU 関連の起動引数を組み立てる。互換性がなければ (None, エラーメッセージ) を返す。

    CPU Solver とメッシングでは GPU 引数を一切付けない。
    Fluent Launcher 起動時は次元・精度を Launcher 側で選ぶため、2D / 精度のチェックは行わない。
    """
    if product == "meshing" or solver_type != "gpu":
        return [], None

    label = version_label or "選択したバージョン"
    if dim == "2d" and not use_launcher:
        return None, "Native GPU Solver は 3D のみ対応しています。3D を選択するか CPU Solver で起動してください。"
    if release is not None and release < GPU_MIN_RELEASE:
        return None, (
            f"{label} は Native GPU Solver に対応していません"
            f"（{format_release(GPU_MIN_RELEASE)} 以降が必要）。CPU Solver で起動してください。"
        )

    args = [GPU_ARG]
    if gpu_remap:
        if release is not None and release < GPU_REMAP_MIN_RELEASE:
            return None, (
                f"{label} は GPU Remapping (-gpu_remap) に対応していません"
                f"（{format_release(GPU_REMAP_MIN_RELEASE)} 以降が必要）。チェックを外してください。"
            )
        args.append(GPU_REMAP_ARG)
    if gpu_hybrid:
        if not dp and not use_launcher:
            return None, "GPU Hybrid Precision は Double Precision (3ddp) と組み合わせて使用します。Double Precision を有効にしてください。"
        if release is not None and release < GPU_HYBRID_MIN_RELEASE:
            return None, (
                f"{label} は GPU Hybrid Precision (-gpu_hybrid_precision) に対応していません"
                f"（{format_release(GPU_HYBRID_MIN_RELEASE)} 以降が必要）。チェックを外してください。"
            )
        args.append(GPU_HYBRID_PRECISION_ARG)
    return args, None


def build_launch_env_overrides(
    base_env: dict,
    japanese: bool,
    gpu_args: list[str],
    use_launcher: bool,
) -> dict:
    """Fluent プロセスにだけ適用する環境変数の差分を作る（PC 全体の環境変数は変更しない）。

    - 日本語 ON: lang=ja（既存の LANG/Lang 等は大文字小文字を無視して置き換え）
    - 日本語 OFF: 何も設定しない（システム環境に従う）
    - FLUENT_LAUNCHER_OPTIONS:
        * Fluent Launcher 起動時 + GPU: -gpu_remap / -gpu_hybrid_precision のうち有効なものを追加
        * 直接起動時: GPU オプションはコマンドライン引数で渡すため、重複しないよう本ツール管理の
          トークンを取り除く（その他の既存オプションは維持）
        * CPU / メッシング: GPU 系トークンを全て取り除く
    """
    overrides: dict[str, str | None] = {}
    if japanese:
        overrides.update(JAPANESE_LANG_ENV)

    existing = get_env_ci(base_env, LAUNCHER_OPTIONS_ENV)
    is_gpu = bool(gpu_args)
    if use_launcher and is_gpu:
        add = [a for a in gpu_args if a != GPU_ARG]
        merged = merge_launcher_options(existing, add, strip_all_gpu=False)
    else:
        if existing is None:
            return overrides
        merged = merge_launcher_options(existing, [], strip_all_gpu=not is_gpu)

    if merged != (existing or ""):
        overrides[LAUNCHER_OPTIONS_ENV] = merged or None
    return overrides


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
    extra_args: list[str] | None = None,
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

        # Native GPU Solver 等の追加引数（例: -gpu -gpu_remap -gpu_hybrid_precision）
        if extra_args:
            cmd.extend(extra_args)

    cmd.extend(["-i", journal_path])

    # 環境変数（日本語起動・Launcher オプション等）を Fluent プロセスにだけ適用して起動。
    # Windows の大文字・小文字非区別に合わせて上書きする。
    env = apply_env_overrides(prepare_external_launch_env(), env_override)

    try:
        subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=env,
            close_fds=True,
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"fluent.exe が見つかりません。バージョン設定のパスを確認してください:\n{fluent_exe}"}
    except PermissionError as e:
        return {"ok": False, "error": f"Fluent を起動する権限がありません:\n{e}"}
    except Exception as e:
        return {"ok": False, "error": f"Fluent の起動に失敗しました:\n{e}"}
    return {"ok": True, "command": cmd}


# -------------------------- JS-API --------------------------

class FluentAPI(WebAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ensure_valid_config()

    # ---- 設定ファイルの健全性 ----
    def _ensure_valid_config(self):
        """JSON の破損・型不正に備える。旧形式 ({"versions": {...}} のみ) もそのまま読み込める。"""
        if self.config_path.exists():
            try:
                json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                # 破損した JSON は上書き前に退避しておく（バージョン登録の手動復旧用）
                try:
                    shutil.copy2(self.config_path, self.config_path.with_name(self.config_path.name + ".broken"))
                except Exception:
                    pass
        if not isinstance(self.data, dict):
            self.data = {"versions": {}}
        versions = self.data.get("versions")
        if not isinstance(versions, dict):
            self.data["versions"] = {}
        else:
            self.data["versions"] = {str(k): str(v) for k, v in versions.items() if isinstance(v, str)}
        if "defaults" in self.data and not isinstance(self.data.get("defaults"), dict):
            self.data.pop("defaults", None)

    # ---- デフォルト設定 ----
    def _current_defaults(self) -> dict:
        return normalize_fluent_settings(self.data.get("defaults"), self.data.get("versions") or {})

    def get_bootstrap(self):
        boot = super().get_bootstrap()
        boot["fluentDefaults"] = self._current_defaults()
        boot["fluentFactoryDefaults"] = normalize_fluent_settings({}, self.data.get("versions") or {})
        boot["hasSavedDefaults"] = isinstance(self.data.get("defaults"), dict)
        boot["fluentGpuRules"] = {
            "gpuMinRelease": GPU_MIN_RELEASE,
            "gpuRemapMinRelease": GPU_REMAP_MIN_RELEASE,
            "gpuHybridMinRelease": GPU_HYBRID_MIN_RELEASE,
        }
        return boot

    def get_defaults(self):
        return {"ok": True, "defaults": self._current_defaults(),
                "hasSavedDefaults": isinstance(self.data.get("defaults"), dict)}

    def save_defaults(self, settings: dict):
        """現在の起動設定をデフォルトとして fluent_versions.json に保存（versions は維持）。"""
        normalized = normalize_fluent_settings(settings, self.data.get("versions") or {})
        self.data["defaults"] = normalized
        try:
            self._persist()
        except Exception as e:
            return {"ok": False, "error": f"設定の保存に失敗しました:\n{e}"}
        return {"ok": True, "defaults": normalized}

    def reset_defaults(self):
        """保存済みのデフォルトを削除し、初期設定を返す（versions は維持）。"""
        self.data.pop("defaults", None)
        try:
            self._persist()
        except Exception as e:
            return {"ok": False, "error": f"設定の保存に失敗しました:\n{e}"}
        return {"ok": True, "defaults": self._current_defaults()}

    # ---- 起動 ----
    def launch(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            payload = {}
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
        if product not in ("solver", "meshing"):
            product = "solver"
        dim = payload.get("dim", "3d")
        if dim not in ("2d", "3d"):
            dim = "3d"
        dp = to_bool(payload.get("dp"), True)
        mode = resolve_mode(product, dim, dp)

        try:
            n_procs = int(payload.get("procs") or 1)
        except (ValueError, TypeError):
            n_procs = 1
        n_procs = max(1, n_procs)

        use_launcher = to_bool(payload.get("useLauncher"), False)
        japanese = to_bool(payload.get("japanese"), False)
        solver_type = payload.get("solverType", "cpu")
        if solver_type not in ("cpu", "gpu"):
            solver_type = "cpu"

        release = detect_fluent_release(ver, exe)
        gpu_args, gpu_error = build_launch_options(
            product,
            dim,
            solver_type,
            to_bool(payload.get("gpuRemap"), False),
            to_bool(payload.get("gpuHybridPrecision"), False),
            dp,
            release,
            ver,
            use_launcher,
        )
        if gpu_error:
            return {"ok": False, "error": gpu_error}

        env_override = build_launch_env_overrides(
            prepare_external_launch_env(), japanese, gpu_args or [], use_launcher
        ) or None

        return launch_fluent(
            exe, mode, product, journal, workdir, n_procs, env_override,
            use_launcher, gpu_args,
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
        height=720,
        min_size=(720, 480),
    )
    api._window = window
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        fatal_error_dialog(APP_TITLE, f"致命的なエラー:\n{e}")
