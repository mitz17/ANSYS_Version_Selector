# ANSYS Version Selector

Windows 上で ANSYS 製品のバージョンを選んで起動するための簡易ツール集です。  
現在は Fluent、SpaceClaim、Workbench 向けの GUI バージョン選択ツールを含みます。

[Ansysのバージョン選択ツールを作った理由｜古い解析ファイルを別バージョンで開くリスクを減らす](https://mitz17.com/blog/ansys-version-selector/)  
開発の経緯や実際のスクショはこちら。

## 注意

このリポジトリは非公式の個人制作ツールです。ANSYS, Fluent, SpaceClaim, Workbench は各権利者に帰属する商標または登録商標です。  
本ツール自体には製品本体は含まれておらず、利用には各製品の正規インストール環境が必要です。

## 免責 / Disclaimer

このツールは現状有姿で提供され、動作保証、特定用途への適合性、継続的なサポートを含むいかなる保証も行いません。  
本ツールの利用または利用不能によって生じたいかなる損害についても、作者は責任を負いません。  
利用者自身の責任で、対象ソフトウェアのライセンス、利用規約、社内ルール等を確認のうえ使用してください。

## 概要

このリポジトリには、`pywebview` + HTML/CSS/JavaScript（`webui/`）ベースの以下のバージョン選択ツールが含まれます。

- `Fluent_Launcher.py`
  Fluent バージョン選択ツールです。バージョン選択、ソルバ/メッシング切替、2D/3D、Double Precision、並列数指定、日本語起動、CPU / Native GPU Solver 切替、起動設定のデフォルト保存に対応します。
- `SpaceClaim_Launcher.py`
  SpaceClaim バージョン選択ツールです。バージョンを選択して、対応ファイルを開きます。
- `Workbench_Launcher.py`
  Workbench バージョン選択ツールです。バージョンを選択して、`.wbpj` プロジェクトを開きます。

各バージョン選択ツールは、バージョン名と実行ファイルパスの対応を JSON 設定ファイルとして保存します。

## 前提条件

- Windows 環境
- Python 3.x
- `pywebview` がインストールされていること（`py -3 -m pip install -r requirements.txt`）
- 各 ANSYS 製品がインストール済みであること

想定インストール先の例:

- `C:\Program Files\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe`
- `C:\Program Files\ANSYS Inc\v252\scdm\SpaceClaim.exe`
- `C:\Program Files\ANSYS Inc\v252\Framework\bin\Win64\RunWB2.exe`

## ファイル構成

- `Fluent_Launcher.py`
- `SpaceClaim_Launcher.py`
- `Workbench_Launcher.py`
- `launcher_common.py`
- `webui/`（`app.html` / `app.css` / `app.js`）
- `requirements.txt`
- `build_all_exe.ps1`
- `tests/`（Fluent 起動処理のユニットテスト）
- `LICENSE`

アイコンファイル:

- `Fluent.ico`
- `Mech.ico`
- `spaceclaim.ico`
- `workbench.ico`

## 使い方

各スクリプトは単体で起動できます。

```powershell
py -3 .\Fluent_Launcher.py
py -3 .\SpaceClaim_Launcher.py
py -3 .\Workbench_Launcher.py
```

ファイルを引数で渡して起動することもできます。

```powershell
py -3 .\Fluent_Launcher.py D:\work\sample.cas.h5
py -3 .\SpaceClaim_Launcher.py D:\cad\part.scdoc
py -3 .\Workbench_Launcher.py D:\project\model.wbpj
```

## Fluent バージョン選択ツール

Fluent バージョン選択ツールは、指定ファイルに応じて一時ジャーナルファイルを生成し、自動読込を行います。

対応拡張子:

- `.msh`
- `.msh.h5`
- `.cas`
- `.cas.h5`
- `.dat`
- `.dat.h5`

主な機能:

- Fluent バージョン選択
- ソルバ / メッシング切替
- 2D / 3D 切替
- Double Precision 指定
- 並列数指定
- 読込ファイルに応じたジャーナル生成
- 日本語 GUI での起動
- CPU Solver / Native GPU Solver の切替（GPU Remapping / GPU Hybrid Precision）
- 起動設定のデフォルト保存・復元

### 起動設定

Fluent 用の設定カードに、以下の項目があります。

| 項目 | 内容 |
| --- | --- |
| 言語: 日本語で起動 | ON のとき Fluent プロセスに環境変数 `lang=ja` を渡します。OFF のときは何も設定せず、システムの環境に従います。 |
| ソルバー種別 | `CPU Solver` / `Native GPU Solver` |
| GPU オプション | `GPU Remapping` / `GPU Hybrid Precision`（Native GPU Solver 選択時のみ表示。初期値はどちらも ON） |

- 環境変数は起動する Fluent プロセスにだけ渡します。PC 全体の環境変数は変更しません。
- Windows では環境変数名の大文字・小文字が区別されないため、既存の `LANG` などは `lang=ja` で置き換えて、重複して渡らないようにしています。
- 以前の版にあった「日本語ロケール（`FLUENT_LANG` / `LANG` / `LC_ALL`）を常に自動適用する」処理は廃止しました。日本語にするかどうかはチェックボックスだけで決まります。
- メッシングを選んだときは GPU 関連の操作が無効になり、従来どおりの引数で起動します。

### Native GPU Solver

Native GPU Solver を選ぶと、起動コマンドに `-gpu` を追加します。

| オプション | 渡す引数 | 対応バージョン |
| --- | --- | --- |
| Native GPU Solver | `-gpu` | 2023 R1 (v231) 以降・3D のみ |
| GPU Remapping | `-gpu_remap` | 2025 R1 (v251) 以降 |
| GPU Hybrid Precision | `-gpu_hybrid_precision` | 2026 R1 (v261) 以降（β 機能、Double Precision と併用） |

- 対応バージョンは、`fluent.exe` のパス（`...\v252\fluent\...`）かバージョン名（`v252`）から判定します。判定できない場合は制限しません。
- 未対応のバージョンでは該当するチェックボックスが無効になり、理由が表示されます。その場合、そのオプションは起動時に渡しません。
- 2D で Native GPU Solver を直接起動しようとした場合や、GPU 非対応のバージョンを選んだ場合は、警告を表示して起動を止めます。

#### `FLUENT_LAUNCHER_OPTIONS` の扱い

- 「Fluentを起動」（直接起動）: GPU オプションはコマンドライン引数で渡します。システムの `FLUENT_LAUNCHER_OPTIONS` に `-gpu_remap` などが入っている場合は、重複しないようにそれらだけを取り除きます。その他のオプションは残します。
- 「Fluent Launcherを起動」: 従来どおり、モード・並列数などの引数は渡さずに Fluent Launcher を表示します。Native GPU Solver を選んでいる場合は、有効な GPU オプションを `FLUENT_LAUNCHER_OPTIONS` に追加します（例: `FLUENT_LAUNCHER_OPTIONS=-gpu_remap -gpu_hybrid_precision`）。既存のオプションは残し、重複は追加しません。Native GPU Solver 自体は、Fluent Launcher の画面で選択してください。
- CPU Solver またはメッシングの場合は、`FLUENT_LAUNCHER_OPTIONS` から GPU 系のオプションを取り除きます。

### 起動コマンドの例

| 設定 | コマンド / 環境変数 |
| --- | --- |
| CPU、3D、Double Precision、8 並列 | `fluent.exe 3ddp -t8 -i <journal>` |
| 上記 + 日本語 | 同上 + 環境変数 `lang=ja` |
| Native GPU（Remapping・Hybrid ON） | `fluent.exe 3ddp -t8 -gpu -gpu_remap -gpu_hybrid_precision -i <journal>` |
| Native GPU + 日本語 | 同上 + 環境変数 `lang=ja` |
| メッシング | `fluent.exe -meshing 3d -t8 -i <journal>` |
| Fluent Launcher（GPU・日本語） | `fluent.exe -i <journal>` + `lang=ja`、`FLUENT_LAUNCHER_OPTIONS=-gpu_remap -gpu_hybrid_precision` |

### デフォルト設定の保存

- 「現在の設定をデフォルトとして保存」を押すと、現在の起動設定を `fluent_versions.json` に保存します。保存されるのは、選択中のバージョン、ソルバ/メッシング、2D/3D、Double Precision、並列数、日本語起動、ソルバー種別、GPU Remapping、GPU Hybrid Precision です。
- 次回起動時は、保存した設定が自動で復元されます。
- 「保存したデフォルトを適用」を押すと、保存した設定（バージョン、CPU/GPU、言語、並列数など）を画面に再適用します。保存内容は変わりません。デフォルトを保存していない間はボタンが無効です。
- 「初期設定にリセット」を押すと、確認のうえ保存済みのデフォルトを削除し、アプリの初期値に戻します。登録済みのバージョンは削除されません。
- 保存したバージョンが削除されている場合は、一覧の先頭のバージョンを選びます。

## SpaceClaim バージョン選択ツール

対応拡張子:

- `.scdoc`
- `.step`
- `.stp`
- `.iges`
- `.igs`

選択したバージョンの実行ファイルに対して、指定ファイルをそのまま渡して起動します。

## Workbench バージョン選択ツール

対応拡張子:

- `.wbpj`

選択したバージョンの Workbench 実行ファイルを `-F <filepath>` 付きで起動します。

PyInstaller で EXE 化した場合は、設定ファイル保存先として `%APPDATA%\AnsysLaunchers` を優先的に使用します。

## 設定ファイル

各バージョン選択ツールは設定を JSON で保存します。

- `fluent_versions.json`
- `spaceclaim_versions.json`
- `workbench_versions.json`

作成タイミング:

- 初回起動時に設定ファイルが存在しなければ作成対象になります。
- 既定のインストール先スキャンで検出結果があれば、その内容で自動保存されます。
- 設定ダイアログで「追加/更新」して「保存して閉じる」を押したときも保存されます。

保存場所:

- `.py` を直接実行する場合は、各スクリプトと同じフォルダ
- PyInstaller で EXE 化した場合は `%APPDATA%\AnsysLaunchers\`

JSON の役割:

- `versions` オブジェクトに「表示名として使うバージョン名」をキーとして保存します。
- 値には、そのバージョンで起動する実行ファイルの絶対パスを保存します。
- 例として Fluent なら `fluent.exe`、SpaceClaim なら `SpaceClaim.exe`、Workbench なら `RunWB2.exe` や `ansyswb.exe` が入ります。

内容の例:

```json
{
  "versions": {
    "v252": "C:\\Program Files\\ANSYS Inc\\v252\\fluent\\ntbin\\win64\\fluent.exe"
  }
}
```

SpaceClaim の例:

```json
{
  "versions": {
    "v252": "C:\\Program Files\\ANSYS Inc\\v252\\scdm\\SpaceClaim.exe"
  }
}
```

Workbench の例:

```json
{
  "versions": {
    "v252": "C:\\Program Files\\ANSYS Inc\\v252\\Framework\\bin\\Win64\\RunWB2.exe"
  }
}
```

Fluent でデフォルト設定を保存した場合の例:

```json
{
  "versions": {
    "v261": "C:\\Program Files\\ANSYS Inc\\v261\\fluent\\ntbin\\win64\\fluent.exe"
  },
  "defaults": {
    "version": "v261",
    "product": "solver",
    "dim": "3d",
    "dp": true,
    "procs": "8",
    "japanese": true,
    "solverType": "gpu",
    "gpuRemap": true,
    "gpuHybridPrecision": true
  }
}
```

補足:

- EXE 版では、旧バージョンが EXE と同じフォルダに保存していた JSON があれば、新しい保存先へコピーして引き継ぎます。
- `defaults` が無い以前の JSON もそのまま読み込めます。`defaults` は、デフォルトを保存したときに追加されます。
- 項目が足りない場合や値が不正な場合は、初期値で補います。JSON が壊れている場合は、元のファイルを `fluent_versions.json.broken` として残してから新しく作り直します。

## Fluent の一時ジャーナル

Fluent バージョン選択ツールは起動時に一時 `.jou` ファイルを作成して `-i` で渡します。

- 保存先は Windows の一時フォルダです。
- ファイル名は `ansys_launcher_*.jou` 形式です。
- 起動直後には削除しません。

理由:

- Fluent 側が起動後にジャーナルを読むため、親プロセス側で即削除すると読込タイミング次第で失敗する可能性があるためです。
- 代わりに、48 時間以上古いこのランチャー由来の一時 `.jou` を、次回起動時に自動掃除します。

## ビルド

PyInstaller を使って、各バージョン選択ツールを Windows 用の単一 EXE に変換できます。

前提:

- Windows
- `python` コマンドが利用可能であること
- `pyinstaller` が利用可能であること

`build_all_exe.ps1` は、`pyinstaller` が見つからない場合のみ `python -m pip install pyinstaller` を実行します。

通常ビルド:

```powershell
.\build_all_exe.ps1
```

クリーンビルド:

```powershell
.\build_all_exe.ps1 -Clean
```

このスクリプトは以下をビルドします。

- `Fluent_Launcher.py` → `dist\FluentVersionSelector.exe`
- `SpaceClaim_Launcher.py` → `dist\SpaceClaimVersionSelector.exe`
- `Workbench_Launcher.py` → `dist\WorkbenchVersionSelector.exe`

各 EXE には、存在する場合は対応する `.ico` ファイルを自動で埋め込みます。

生成される主なファイル:

- `dist\*.exe`
- `build\...`
- `*.spec`

これらの生成物は `.gitignore` で除外しています。

注意:

- 初回ビルドでは PyInstaller の解析により数十秒程度かかることがあります。
- 単一 EXE の `onefile` でビルドします。
- 一時展開まわりの Windows 側干渉を減らすため、UPX 圧縮は使っていません。
- ビルド後の動作確認は、各 EXE を直接起動して行ってください。
- 画面ファイル（`webui/`）は `--add-data` で EXE に同梱します。

## テスト

Fluent の起動コマンド・環境変数・設定の保存は、`subprocess.Popen` をモックしたユニットテストで確認できます（Fluent 本体と pywebview は不要です）。

```powershell
py -3 -m unittest discover -s tests -v
```

## ライセンス

MIT License。詳細は `LICENSE` を参照してください。
