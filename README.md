# pymic

音声入力（マイク）を受けて文字起こしを行うアプリケーションです。UI は `pywebview` を利用しています。パッケージ構成で提供しており、`python -m pymic` での起動を推奨します。従来の互換性のため `python main.py` でも起動できます。

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
- 出力は `dist\\main.exe`（`--onefile`）または `dist\\main\\`（`--onedir`）になります。

実行例:

```powershell
.\\dist\\main.exe
# または
.\\dist\\main\\main.exe
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
