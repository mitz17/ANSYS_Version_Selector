# -*- coding: utf-8 -*-
"""Fluent バージョン選択ツールの起動コマンド・環境変数・設定保存のテスト。

実際の Fluent が無い環境でも動くよう、subprocess.Popen をモック化して
組み立てられたコマンドと環境変数を検証する。pywebview も不要（スタブを差し込む）。

実行方法（リポジトリ直下で）:
    py -3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# pywebview が未インストールの環境でも import できるようにスタブ化
if "webview" not in sys.modules:
    try:
        import webview  # noqa: F401
    except Exception:
        stub = types.ModuleType("webview")
        stub.FileDialog = types.SimpleNamespace(OPEN=0)
        stub.create_window = lambda *a, **k: None
        stub.start = lambda *a, **k: None
        sys.modules["webview"] = stub

import launcher_common  # noqa: E402
import Fluent_Launcher as FL  # noqa: E402
import SpaceClaim_Launcher as SC  # noqa: E402
import Workbench_Launcher as WB  # noqa: E402


class LauncherTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg_dir = self.tmp / "cfg"
        self.cfg_dir.mkdir()
        # 設定ファイルをテスト用の一時フォルダに向ける
        self.work = self.tmp / "work"
        self.work.mkdir()
        self._patches = [
            mock.patch.object(launcher_common, "app_base_dir", return_value=self.cfg_dir),
            mock.patch.object(launcher_common, "config_base_dir", return_value=self.cfg_dir),
            # テストは os.environ をクリアするため、実行環境（特に Windows）の
            # USERPROFILE 等に依存する Path.home() が失敗しないよう固定する
            mock.patch.object(FL.Path, "home", return_value=self.work),
        ]
        for p in self._patches:
            p.start()
        # 擬似 fluent.exe（パスにリリース番号を含める）
        self.exes = {}
        for rel in ("v222", "v242", "v252", "v261"):
            exe = self.tmp / "ANSYS Inc" / rel / "fluent" / "ntbin" / "win64" / "fluent.exe"
            exe.parent.mkdir(parents=True)
            exe.write_text("")
            self.exes[rel] = str(exe)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def write_config(self, data):
        (self.cfg_dir / FL.CONFIG_NAME).write_text(
            data if isinstance(data, str) else json.dumps(data), encoding="utf-8"
        )

    def read_config(self) -> dict:
        return json.loads((self.cfg_dir / FL.CONFIG_NAME).read_text(encoding="utf-8"))

    def make_api(self) -> FL.FluentAPI:
        return FL.FluentAPI(
            config_name=FL.CONFIG_NAME,
            app_title=FL.APP_TITLE,
            app_kind="fluent",
            find_versions_callback=lambda: {},
            browse_filetypes=("Executable (fluent.exe)",),
        )

    def launch(self, api=None, base_env=None, **payload):
        """Popen をモックして launch し、(結果, cmd, env, journal内容) を返す。"""
        api = api or self._default_api()
        body = {"version": "v261", "product": "solver", "dim": "3d", "dp": True, "procs": "8"}
        body.update(payload)
        env = dict(base_env if base_env is not None else {"PATH": "/bin", "SYSTEMROOT": "C:\\Windows"})
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(FL.subprocess, "Popen") as popen:
            res = api.launch(body)
        if not popen.called:
            return res, None, None, None
        cmd = popen.call_args.args[0]
        kwargs = popen.call_args.kwargs
        jpath = cmd[cmd.index("-i") + 1]
        journal = Path(jpath).read_text(encoding="utf-8")
        os.unlink(jpath)
        return res, cmd, kwargs["env"], journal

    def _default_api(self):
        self.write_config({"versions": self.exes})
        return self.make_api()


class TestJapaneseLaunch(LauncherTestBase):
    def test_01_japanese_on_passes_lang_ja(self):
        res, cmd, env, _ = self.launch(japanese=True, base_env={"PATH": "/bin", "LANG": "en_US.UTF-8"})
        self.assertTrue(res["ok"], res)
        self.assertEqual(env.get("lang"), "ja")
        # 大文字小文字違いの LANG が重複して残らない（Windows 対策）
        self.assertEqual([k for k in env if k.upper() == "LANG"], ["lang"])

    def test_02_japanese_off_does_not_force_locale(self):
        res, cmd, env, _ = self.launch(japanese=False, base_env={"PATH": "/bin", "LANG": "en_US.UTF-8"})
        self.assertTrue(res["ok"], res)
        self.assertNotIn("lang", env)
        self.assertEqual(env.get("LANG"), "en_US.UTF-8")  # システム環境のまま
        for key in ("FLUENT_LANG", "LC_ALL"):  # 旧 PREFERRED_LOCALE_ENV の自動適用が無いこと
            self.assertNotIn(key, env)

    def test_02b_japanese_off_without_any_lang(self):
        res, cmd, env, _ = self.launch(base_env={"PATH": "/bin"})
        self.assertTrue(res["ok"], res)
        self.assertFalse([k for k in env if k.upper() in ("LANG", "FLUENT_LANG", "LC_ALL")])

    def test_env_override_is_case_insensitive(self):
        env = FL.apply_env_overrides({"LANG": "en", "Lang": "x", "PATH": "p"}, {"lang": "ja"})
        self.assertEqual(env, {"PATH": "p", "lang": "ja"})
        env = FL.apply_env_overrides({"fluent_launcher_options": "-a"}, {"FLUENT_LAUNCHER_OPTIONS": None})
        self.assertEqual(env, {})

    def test_process_env_only(self):
        """PC 全体（このプロセス）の環境変数は変更しない。"""
        with mock.patch.dict(os.environ, {"PATH": "/bin"}, clear=True):
            api = self._default_api()
            with mock.patch.object(FL.subprocess, "Popen"):
                api.launch({"version": "v261", "japanese": True, "solverType": "gpu",
                            "gpuRemap": True, "gpuHybridPrecision": True, "useLauncher": True})
            self.assertNotIn("lang", os.environ)
            self.assertNotIn("FLUENT_LAUNCHER_OPTIONS", os.environ)


class TestGpuLaunch(LauncherTestBase):
    def test_03_gpu_adds_flag(self):
        res, cmd, env, _ = self.launch(solverType="gpu", gpuRemap=False, gpuHybridPrecision=False)
        self.assertTrue(res["ok"], res)
        self.assertEqual(cmd[1:4], ["3ddp", "-t8", "-gpu"])
        self.assertEqual(cmd[4], "-i")

    def test_04_cpu_has_no_gpu_options(self):
        res, cmd, env, _ = self.launch(
            solverType="cpu", gpuRemap=True, gpuHybridPrecision=True,
            base_env={"PATH": "/bin", "FLUENT_LAUNCHER_OPTIONS": "-foo -gpu_remap -gpu=1,2 -bar"},
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(cmd[1:3], ["3ddp", "-t8"])
        self.assertFalse([a for a in cmd if a.startswith("-gpu")])
        # 既存のその他オプションは維持し、GPU 専用オプションだけ外す
        self.assertEqual(env["FLUENT_LAUNCHER_OPTIONS"], "-foo -bar")

    def test_05_remap_hybrid_combinations(self):
        for remap in (False, True):
            for hybrid in (False, True):
                with self.subTest(remap=remap, hybrid=hybrid):
                    res, cmd, env, _ = self.launch(solverType="gpu", gpuRemap=remap, gpuHybridPrecision=hybrid)
                    self.assertTrue(res["ok"], res)
                    gpu_args = [a for a in cmd if a.startswith("-gpu")]
                    expected = ["-gpu"] + (["-gpu_remap"] if remap else []) + \
                        (["-gpu_hybrid_precision"] if hybrid else [])
                    self.assertEqual(gpu_args, expected)

    def test_direct_gpu_dedupes_existing_env(self):
        res, cmd, env, _ = self.launch(
            solverType="gpu", gpuRemap=True, gpuHybridPrecision=False,
            base_env={"PATH": "/bin", "FLUENT_LAUNCHER_OPTIONS": "-gpu_remap -foo"},
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(cmd.count("-gpu_remap"), 1)
        self.assertEqual(env["FLUENT_LAUNCHER_OPTIONS"], "-foo")

    def test_direct_gpu_env_removed_when_only_managed_tokens(self):
        res, cmd, env, _ = self.launch(
            solverType="gpu", base_env={"PATH": "/bin", "FLUENT_LAUNCHER_OPTIONS": "-gpu_remap"},
        )
        self.assertNotIn("FLUENT_LAUNCHER_OPTIONS", env)

    def test_launcher_mode_gpu_uses_env(self):
        res, cmd, env, _ = self.launch(
            useLauncher=True, japanese=True, solverType="gpu", gpuRemap=True, gpuHybridPrecision=True,
            base_env={"PATH": "/bin", "fluent_launcher_options": "-foo -gpu_remap"},
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(cmd[1], "-i")  # Launcher 表示時はモード等の引数を渡さない（従来どおり）
        self.assertEqual(env["FLUENT_LAUNCHER_OPTIONS"], "-foo -gpu_remap -gpu_hybrid_precision")
        self.assertEqual([k for k in env if k.upper() == "FLUENT_LAUNCHER_OPTIONS"], ["FLUENT_LAUNCHER_OPTIONS"])
        self.assertEqual(env["lang"], "ja")

    def test_launcher_mode_partial_options(self):
        res, cmd, env, _ = self.launch(useLauncher=True, solverType="gpu", gpuRemap=False, gpuHybridPrecision=True)
        self.assertEqual(env["FLUENT_LAUNCHER_OPTIONS"], "-gpu_hybrid_precision")
        res, cmd, env, _ = self.launch(useLauncher=True, solverType="gpu", gpuRemap=False, gpuHybridPrecision=False)
        self.assertNotIn("FLUENT_LAUNCHER_OPTIONS", env)

    def test_launcher_mode_cpu_no_gpu_env(self):
        res, cmd, env, _ = self.launch(useLauncher=True, solverType="cpu", gpuRemap=True, gpuHybridPrecision=True)
        self.assertTrue(res["ok"], res)
        self.assertNotIn("FLUENT_LAUNCHER_OPTIONS", env)

    def test_japanese_and_gpu(self):
        res, cmd, env, _ = self.launch(japanese=True, solverType="gpu", gpuRemap=True, gpuHybridPrecision=True)
        self.assertTrue(res["ok"], res)
        self.assertEqual(env["lang"], "ja")
        self.assertEqual(cmd[1:6], ["3ddp", "-t8", "-gpu", "-gpu_remap", "-gpu_hybrid_precision"])

    def test_incompatible_combinations_are_blocked(self):
        cases = [
            (dict(version="v261", dim="2d", solverType="gpu"), "3D"),
            (dict(version="v222", solverType="gpu", gpuRemap=False, gpuHybridPrecision=False), "2023 R1"),
            (dict(version="v242", solverType="gpu", gpuRemap=True, gpuHybridPrecision=False), "2025 R1"),
            (dict(version="v252", solverType="gpu", gpuRemap=False, gpuHybridPrecision=True), "2026 R1"),
            (dict(version="v261", dp=False, solverType="gpu", gpuRemap=False, gpuHybridPrecision=True), "Double Precision"),
        ]
        for body, word in cases:
            with self.subTest(body=body):
                res, cmd, env, _ = self.launch(**body)
                self.assertFalse(res["ok"])
                self.assertIn(word, res["error"])
                self.assertIsNone(cmd)  # Popen は呼ばれない

    def test_supported_older_versions(self):
        res, cmd, *_ = self.launch(version="v252", solverType="gpu", gpuRemap=True, gpuHybridPrecision=False)
        self.assertTrue(res["ok"], res)
        self.assertEqual([a for a in cmd if a.startswith("-gpu")], ["-gpu", "-gpu_remap"])
        res, cmd, *_ = self.launch(version="v242", solverType="gpu", gpuRemap=False, gpuHybridPrecision=False)
        self.assertTrue(res["ok"], res)

    def test_release_detection(self):
        self.assertEqual(FL.detect_fluent_release("x", r"C:\Program Files\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe"), 252)
        self.assertEqual(FL.detect_fluent_release("v261", ""), 261)
        self.assertEqual(FL.detect_fluent_release("2025R1", r"D:\tools\fluent.exe"), None)
        self.assertEqual(FL.detect_fluent_release("Fluent v242 (test)", ""), 242)

    def test_unknown_release_is_allowed(self):
        exe = self.tmp / "custom" / "fluent.exe"
        exe.parent.mkdir()
        exe.write_text("")
        self.write_config({"versions": {"mybuild": str(exe)}})
        res, cmd, *_ = self.launch(api=self.make_api(), version="mybuild", solverType="gpu",
                                   gpuRemap=True, gpuHybridPrecision=True)
        self.assertTrue(res["ok"], res)

    def test_popen_failure_message(self):
        api = self._default_api()
        with mock.patch.object(FL.subprocess, "Popen", side_effect=FileNotFoundError("x")):
            res = api.launch({"version": "v261"})
        self.assertFalse(res["ok"])
        self.assertIn("fluent.exe", res["error"])


class TestDefaults(LauncherTestBase):
    def test_06_save_and_restore_after_restart(self):
        api = self._default_api()
        settings = {
            "version": "v252", "product": "solver", "dim": "2d", "dp": False, "procs": "12",
            "japanese": True, "solverType": "gpu", "gpuRemap": False, "gpuHybridPrecision": True,
        }
        res = api.save_defaults(settings)
        self.assertTrue(res["ok"], res)
        # 「再起動」= 新しい API インスタンス
        boot = self.make_api().get_bootstrap()
        self.assertEqual(boot["fluentDefaults"], settings)
        self.assertTrue(boot["hasSavedDefaults"])

    def test_07_legacy_json_migration_keeps_versions(self):
        legacy = {"versions": {"v252": self.exes["v252"], "v261": self.exes["v261"]}}
        self.write_config(legacy)
        api = self.make_api()
        boot = api.get_bootstrap()
        self.assertEqual(boot["versions"], legacy["versions"])
        self.assertEqual(boot["fluentDefaults"]["version"], "v252")  # 先頭バージョン
        self.assertFalse(boot["hasSavedDefaults"])
        api.save_defaults({"version": "v261", "japanese": True})
        data = self.read_config()
        self.assertEqual(data["versions"], legacy["versions"])
        self.assertEqual(list(data["versions"]), ["v252", "v261"])  # 並び順も維持
        self.assertEqual(data["defaults"]["version"], "v261")
        self.assertTrue(data["defaults"]["japanese"])

    def test_apply_saved_defaults(self):
        api = self._default_api()
        res = api.get_defaults()
        self.assertFalse(res["ok"])  # 未保存のときは適用できない
        self.assertFalse(res["hasSavedDefaults"])
        saved = {"version": "v252", "procs": "12", "japanese": True, "solverType": "gpu", "gpuRemap": False}
        api.save_defaults(saved)
        before = self.read_config()
        res = api.get_defaults()
        self.assertTrue(res["ok"])
        self.assertEqual(res["missingVersion"], "")
        for k, v in saved.items():
            self.assertEqual(res["defaults"][k], v)
        self.assertEqual(self.read_config(), before)  # 適用しても保存内容は変わらない
        # 保存したバージョンが削除された場合はフォールバックし、元の名前を返す
        api.delete_version("v252")
        res = api.get_defaults()
        self.assertTrue(res["ok"])
        self.assertEqual(res["missingVersion"], "v252")
        self.assertEqual(res["defaults"]["version"], "v222")
        self.assertTrue(res["defaults"]["japanese"])

    def test_reset_defaults_keeps_versions(self):
        api = self._default_api()
        api.save_defaults({"version": "v252", "japanese": True})
        res = api.reset_defaults()
        self.assertTrue(res["ok"])
        self.assertFalse(res["defaults"]["japanese"])
        data = self.read_config()
        self.assertNotIn("defaults", data)
        self.assertEqual(data["versions"], self.exes)
        self.assertFalse(api.get_defaults()["ok"])

    def test_deleted_version_falls_back(self):
        api = self._default_api()
        api.save_defaults({"version": "v252"})
        api.delete_version("v252")
        boot = self.make_api().get_bootstrap()
        self.assertIn(boot["fluentDefaults"]["version"], boot["versions"])
        self.assertEqual(boot["fluentDefaults"]["version"], "v222")
        # バージョンが 1 つも無い場合
        self.write_config({"versions": {}, "defaults": {"version": "v252"}})
        self.assertEqual(self.make_api().get_bootstrap()["fluentDefaults"]["version"], "")

    def test_broken_or_partial_json(self):
        self.write_config("{ this is not json")
        api = self.make_api()
        self.assertEqual(api.get_bootstrap()["versions"], {})
        self.assertTrue((self.cfg_dir / (FL.CONFIG_NAME + ".broken")).exists())
        # 型が不正・値が不足していても既定値で補う
        self.write_config({"versions": {"v261": self.exes["v261"]},
                           "defaults": {"dim": "4d", "procs": "abc", "dp": "false", "solverType": 1}})
        d = self.make_api().get_bootstrap()["fluentDefaults"]
        self.assertEqual(d, dict(FL.FACTORY_DEFAULTS, version="v261", dp=False))
        self.write_config({"versions": [], "defaults": "x"})
        boot = self.make_api().get_bootstrap()
        self.assertEqual(boot["versions"], {})
        self.write_config([1, 2, 3])
        self.assertEqual(self.make_api().get_bootstrap()["versions"], {})


class TestExistingBehaviour(LauncherTestBase):
    def test_08_h5_journal_loading(self):
        cas = self.work / "model.cas.h5"
        dat = self.work / "model.dat.h5"
        msh = self.work / "mesh.msh.h5"
        for f in (cas, dat, msh):
            f.write_text("")
        _, cmd, _, j = self.launch(file=str(cas))
        self.assertEqual(j, f'/file/read-case "{cas}"\n/file/read-data "{dat}"\n')
        _, _, _, j = self.launch(file=str(dat))
        self.assertEqual(j, f'/file/read-case "{cas}"\n/file/read-data "{dat}"\n')
        _, _, _, j = self.launch(file=str(msh))
        self.assertEqual(j, f'/file/read-mesh "{msh}"\n')
        # GPU 起動でもジャーナル読込は同じ
        _, cmd, _, j = self.launch(file=str(cas), solverType="gpu")
        self.assertIn("-gpu", cmd)
        self.assertIn("/file/read-case", j)

    def test_09_meshing_mode(self):
        for st in ("cpu", "gpu"):
            with self.subTest(solverType=st):
                res, cmd, env, j = self.launch(product="meshing", solverType=st, gpuRemap=True,
                                               gpuHybridPrecision=True, dim="2d")
                self.assertTrue(res["ok"], res)
                self.assertEqual(cmd[1:4], ["-meshing", "3d", "-t8"])
                self.assertFalse([a for a in cmd if a.startswith("-gpu")])
                self.assertEqual(j, "\n")

    def test_cpu_default_command(self):
        res, cmd, env, _ = self.launch()
        self.assertEqual(cmd[0], self.exes["v261"])
        self.assertEqual(cmd[1:3], ["3ddp", "-t8"])
        res, cmd, env, _ = self.launch(procs="1", dp=False, dim="2d")
        self.assertEqual(cmd[1:3], ["2d", "-i"])

    def test_old_payload_without_new_keys(self):
        """新しいキーを含まない旧 UI からの payload でも従来どおり CPU 起動する。"""
        res, cmd, env, _ = self.launch()
        self.assertTrue(res["ok"])
        self.assertFalse([a for a in cmd if a.startswith("-gpu")])
        self.assertNotIn("lang", env)


class TestOtherLaunchersUnaffected(LauncherTestBase):
    def test_10_spaceclaim_and_workbench(self):
        exe = self.tmp / "app.exe"
        exe.write_text("")
        doc = self.work / "part.scdoc"
        doc.write_text("")
        for mod, func in ((SC, "launch_spaceclaim"), (WB, "launch_workbench")):
            with self.subTest(module=mod.__name__), \
                    mock.patch.dict(os.environ, {"PATH": "/bin", "LANG": "en_US"}, clear=True), \
                    mock.patch.object(mod.subprocess, "Popen") as popen:
                res = getattr(mod, func)(str(exe), str(doc), self.work)
                self.assertTrue(res["ok"])
                cmd = popen.call_args.args[0]
                env = popen.call_args.kwargs["env"]
                self.assertEqual(cmd[0], str(exe))
                self.assertFalse([a for a in cmd if "gpu" in a])
                self.assertEqual(env.get("LANG"), "en_US")
                self.assertNotIn("lang", env)
                self.assertNotIn("FLUENT_LAUNCHER_OPTIONS", env)


if __name__ == "__main__":
    unittest.main()
