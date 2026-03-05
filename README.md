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
````markdown
簡単な pywebview デモアプリです。

プロジェクトはパッケージ構成になりました。推奨の起動方法:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pymic    # 推奨: パッケージとして実行
# 既存のワークフロー互換のため、従来通り `python main.py` でも起動できます
```

ファイル構成の主な変更点:
- [pymic/](pymic) - アプリ本体のパッケージ（`app.py`, `api.py`, `__main__.py` など）
- [main.py](main.py) - 互換シム（従来の起動方法を壊さないための薄いラッパー）
- [web/index.html](web/index.html) - UI 資産

必要に応じて `pywebview` の GUI バックエンド（例: `pywebview[qt]`）を指定してください。

PyInstaller でのビルド
-------------------

Windows 環境で本プロジェクトを単一実行ファイル（またはフォルダ）にパッケージする例です。プロジェクトルートで実行してください。`web` ディレクトリを実行ファイルに含めるために `--add-data` オプションを使います（Windows のパス区切りは `;` を使います）。

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

## 開発ルール

- コードをコミットする前に、必ずフォーマットを整えてください:

```powershell
ruff format .
```

このリポジトリでは `ruff` をコードフォーマットに使用します。まだインストールしていない場合は、開発環境にインストールしてください（例: `pip install ruff`）。

---

## 追加情報

プロジェクトの概要、起動方法、ビルド手順は以下の通りです。

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
- [pymic/](pymic)

パッケージとして起動する推奨方法:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pymic
# 互換性のため `python main.py` でも起動可能
```

PyInstaller でのビルド (Windows 例):

```powershell
pip install pyinstaller
pyinstaller --onefile --noconsole --add-data "web;web" main.py
```

ビルド後の実行例:

```powershell
.\dist\main.exe
# または
.\dist\main\main.exe
```

