# ANSYS Version Selector

Windows 上で ANSYS 製品のバージョンを選んで起動するための簡易ツール集です。  
現在は Fluent、SpaceClaim、Workbench 向けの GUI バージョン選択ツールを含みます。

[Ansysのバージョン選択ツールを作った理由｜古い解析ファイルを別バージョンで開くリスクを減らす](https://mitz17.com/blog/ansys-version-selector/)  
開発の経緯や実際のスクショはこちら。

## 注意

このリポジトリは非公式の個人制作ツールです。ANSYS, Fluent, SpaceClaim, Workbench は各権利者に帰属する商標または登録商標です。  
本ツール自体には製品本体は含まれておらず、利用には各製品の正規インストール環境が必要です。

## 概要

このリポジトリには、`tkinter` ベースの以下のバージョン選択ツールが含まれます。

- `Fluent_Launcher_from_md.py`
  Fluent バージョン選択ツールです。バージョン選択、ソルバ/メッシング切替、2D/3D、Double Precision、並列数指定に対応します。
- `SpaceClaim_Launcher.py`
  SpaceClaim バージョン選択ツールです。バージョンを選択して、対応ファイルを開きます。
- `Workbench_Launcher.py`
  Workbench バージョン選択ツールです。バージョンを選択して、`.wbpj` プロジェクトを開きます。

各バージョン選択ツールは、バージョン名と実行ファイルパスの対応を JSON 設定ファイルとして保存します。

## 前提条件

- Windows 環境
- Python 3.x
- `tkinter` が利用可能であること
- 各 ANSYS 製品がインストール済みであること

想定インストール先の例:

- `C:\Program Files\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe`
- `C:\Program Files\ANSYS Inc\v252\scdm\SpaceClaim.exe`
- `C:\Program Files\ANSYS Inc\v252\Framework\bin\Win64\RunWB2.exe`

## ファイル構成

- `Fluent_Launcher_from_md.py`
- `SpaceClaim_Launcher.py`
- `Workbench_Launcher.py`
- `launcher_common.py`
- `README_Fluent_Launcher.md`
- `build_all_exe.ps1`
- `LICENSE`

アイコンファイル:

- `Fluent.ico`
- `Mech.ico`
- `spaceclaim.ico`
- `workbench.ico`

## 使い方

各スクリプトは単体で起動できます。

```powershell
py -3 .\Fluent_Launcher_from_md.py
py -3 .\SpaceClaim_Launcher.py
py -3 .\Workbench_Launcher.py
```

ファイルを引数で渡して起動することもできます。

```powershell
py -3 .\Fluent_Launcher_from_md.py D:\work\sample.cas.h5
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

詳細は `README_Fluent_Launcher.md` を参照してください。

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

補足:

- EXE 版では、旧バージョンが EXE と同じフォルダに保存していた JSON があれば、新しい保存先へコピーして引き継ぎます。

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

- `Fluent_Launcher_from_md.py` → `dist\FluentVersionSelector.exe`
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
- ビルド後の動作確認は、各 EXE を直接起動して行ってください。

## ライセンス

MIT License。詳細は `LICENSE` を参照してください。
