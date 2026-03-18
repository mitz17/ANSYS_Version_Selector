# Fluent バージョン選択ツール 使い方

- 対象: Ansys Fluent の複数バージョンから選んで起動したい方向けの簡易ランチャー。
- 方式: `tkinter` のGUIでバージョン・製品モード・2D/3D・DP・並列数を指定し、`fluent.exe` を所定の引数で起動します。
- 既定拡張子: `.msh`, `.msh.h5`, `.cas`, `.cas.h5`, `.dat`, `.dat.h5` を読み込み対象として扱えます。

## 前提条件
- Windows 環境で Ansys Fluent がインストール済みであること。
- `fluent.exe` のパス例: `C:\\Program Files\\ANSYS Inc\\v252\\fluent\\ntbin\\win64\\fluent.exe`
- Python 3.x が導入済みで、`tkinter` が利用可能であること。

## 起動方法
- ダブルクリック: `Fluent_Launcher_from_md.py` をダブルクリックして起動。
- コマンドライン: `python Fluent_Launcher_from_md.py [オプション: 読み込みたいファイルパス]`
  - 例: `python Fluent_Launcher_from_md.py D:\\work\\model\\case.cas.h5`

## 初期設定（バージョン登録）
初回起動時、`fluent_versions.json` が作成されます。
- `.py` 版では本スクリプトと同じフォルダに保存されます。
- EXE 版では `%APPDATA%\\AnsysLaunchers\\` に保存されます。
- 右側の「設定…」を開き、以下を操作します。
  - バージョン名: 例 `v252` など任意文字列
  - `fluent.exe` のパス: 実行ファイルを参照して指定
  - 「追加/更新」で登録、「削除」で削除
  - 「スキャン」で既定パス配下（`C:\\Program Files\\ANSYS Inc`, `C:\\Program Files\\Ansys Inc`）から自動検出
  - 「保存して閉じる」で反映

登録後、メイン画面の「Fluent バージョン」コンボボックスに候補が表示されます。

## 使い方
1. 読み込みファイル（任意）
   - 「参照…」で `.msh/.cas/.dat`（および `.h5` 併用拡張）を選択。
   - 指定しない場合は空のジャーナルで起動します。
2. バージョン選択
   - 「Fluent バージョン」から登録済みのバージョンを選択。
3. 製品モード
   - ソルバ: 通常の Fluent ソルバを起動。読み込みファイルがあれば自動で読み込みます。
   - メッシング: `-meshing` で起動。読み込みファイルの自動読込は行いません。
4. 次元・精度（ソルバ時のみ有効）
   - 2D/3D、Double Precision を選択。内部的に `2d|3d` + `dp` を引数として付与。
5. 並列プロセス数
   - `-t<N>` を付与（`N > 1` のとき）。例: `-t8`。
6. 「Fluent を起動」をクリック
   - 作業ディレクトリは、読み込みファイルを指定した場合はその親フォルダ、未指定時はユーザホーム。

## 自動ジャーナルの挙動（ソルバ）
- 起動時に一時ジャーナル（`.jou`）を生成して `-i` で渡します。
- 一時ジャーナルは Windows の一時フォルダに `ansys_launcher_*.jou` 形式で作成されます。
- 起動直後には削除せず、48 時間以上古いものを次回起動時に自動削除します。
- SI 単位系設定後、拡張子に応じて下記のいずれかを実行します。
  - `.msh/.msh.h5`: `/file/read-mesh "<path>"`
  - `.cas/.cas.h5`: `/file/read-case "<path>"`
  - `.dat/.dat.h5`: `/file/read-data "<path>"`
- 上記に該当しない場合は `/report/system/proc-mem` のみ実行。
- メッシングモードではジャーナルは空（自動読込なし）。

## コマンドラインと既定アプリの活用
- コマンドライン引数にファイルパスを渡すと、GUI起動時にそのファイルがセットされます。
- OS の「既定のアプリ」で `.cas/.dat/.msh` を本スクリプトに関連付けると、該当ファイルのダブルクリックで本ランチャーが開き、バージョン選択後 Fluent を起動できます。

## 例：起動時に付与される主な引数
- ソルバ 3D DP 8並列、データ読込: `fluent.exe 3ddp -t8 -i <temp.jou>`
- メッシング 3D 8並列（ランチャ回避のため 2D/3D を付与）: `fluent.exe -meshing 3d -t8 -i <temp.jou>`

## 設定ファイル `fluent_versions.json`
- 保存場所:
  - `.py` 版: `Fluent_Launcher_from_md.py` と同じフォルダ
  - EXE 版: `%APPDATA%\\AnsysLaunchers\\`
- フォーマット:
  {
    "versions": {
      "v252": "C:\\\Program Files\\\\ANSYS Inc\\\\v252\\\\fluent\\\\ntbin\\\\win64\\\\fluent.exe",
      "v242": "C:\\\Program Files\\\\ANSYS Inc\\\\v242\\\\fluent\\\\ntbin\\\\win64\\\\fluent.exe"
    }
  }
- 直接編集しても構いません（GUI からの編集を推奨）。

## トラブルシューティング
- 起動できない/エラーになる
  - 「設定…」で選択中バージョンの `fluent.exe` パスが実在するか確認
  - 管理者権限不要ですが、ウイルス対策でブロックされる場合は除外設定を検討
- ファイルが読み込まれない
  - ソルバモードになっているか、拡張子が対応しているか確認
  - `.h5` 併用拡張（例: `.cas.h5`）は自動判定されます
- 文字化け表示
  - 本 README の表示や IDE に依存。アプリ自体の動作には影響しません。

## ライセンス/免責
- 本スクリプトは個人利用想定のツールです。各社ソフトウェアのライセンス遵守の上でご利用ください。
