簡単な pywebview デモアプリです。

準備と実行:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

ファイル:
- [main.py](main.py)
- [web/index.html](web/index.html)

必要に応じて `pywebview` の GUI バックエンド（例: `pywebview[qt]`）を指定してください。

PyInstaller でのビルド
-------------------

Windows 環境で本プロジェクトを単一実行ファイル（またはフォルダ）にパッケージする例です。プロジェクトルート（この `README.md` と同じディレクトリ）で実行してください。`web` ディレクトリを実行ファイルに含めるために `--add-data` オプションを使います（Windows のパス区切りは `;` を使います）。

1) PyInstaller のインストール

```powershell
pip install pyinstaller
```

2) 単一ファイル（exe）を作る（配布向け、サイズ大）

```powershell
pyinstaller --onefile --noconsole --add-data "web;web" main.py
```

3) ワンフォルダ（デバッグや開発向け、ファイルが分かれて出力される）

```powershell
pyinstaller --onedir --noconsole --add-data "web;web" main.py
```

注意点:
- `--add-data "web;web"` はプロジェクト内の `web` フォルダを実行時の作業ディレクトリ側の `web` サブフォルダとして含めます。Linux/macOS では区切りに `:` を使います（例: `--add-data "web:web"`）。
- `--noconsole` を外すとコンソールが表示されます（デバッグ時は外すと便利）。
- 出力バイナリは `dist\main.exe`（`--onefile`）または `dist\main\`（`--onedir`）に生成されます。
- アイコン追加や追加の依存ファイルがある場合は PyInstaller のドキュメントを参照してください。

ビルド後の動作確認:

```powershell
# 単一ファイルの場合
.\dist\main.exe

# ワンフォルダの場合
.\dist\main\main.exe
```

