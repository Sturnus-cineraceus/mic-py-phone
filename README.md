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
# pymic

簡単な pywebview デモアプリケーションです。パッケージ構成で提供しており、`python -m pymic` での起動を推奨します。従来の互換性のため `python main.py` でも起動できます。

---

## クイックスタート

1. 仮想環境の作成と有効化（PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. 依存関係のインストール

```powershell
pip install -r requirements.txt
```

3. 起動

```powershell
python -m pymic
# 互換性のため: python main.py
```

---

## ファイル構成（主なもの）

- [main.py](main.py) — 互換用の薄いラッパー
- [pymic/](pymic) — アプリ本体（`app.py`, `api.py`, `__main__.py` など）
- [web/index.html](web/index.html) — UI 資産

必要に応じて `pywebview` の GUI バックエンド（例: `pywebview[qt]`）を指定してください。

---

## PyInstaller でのビルド（Windows 例）

1. PyInstaller をインストール

```powershell
pip install pyinstaller
```

2. 単一ファイル（配布向け）

```powershell
pyinstaller --onefile --noconsole --add-data "web;web" main.py
```

3. ワンフォルダ（開発向け）

```powershell
pyinstaller --onedir --noconsole --add-data "web;web" main.py
```

注意点:
- `--add-data "web;web"` は実行時に `web` フォルダを含めます。Linux/macOS の場合は `:` を区切りに使用します（例: `--add-data "web:web"`）。
- デバッグ時は `--noconsole` を外すとコンソール出力が見えて便利です。
- 出力は `dist\main.exe`（`--onefile`）または `dist\main\`（`--onedir`）になります。

実行例:

```powershell
.\dist\main.exe
# または
.\dist\main\main.exe
```

---

## 開発ルール

- **コミット前にフォーマットを実行**: コードをコミットする前に、必ず次のコマンドでフォーマットを行ってください。

```powershell
ruff format .
```

このリポジトリでは `ruff` をフォーマッタとして利用します。未インストールの場合は `pip install ruff` で導入してください。

---

## 追加情報

必要に応じて、`pywebview` のバックエンドや PyInstaller のオプションを調整してください。問題があれば Issue を作成してください。

