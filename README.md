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

---

## 音質調整の目安（ノイズ対策）

- ノイズゲート閾値: `-90`〜`0` dB の範囲で調整可能（初期値 `-40` dB）
- ノイズリダクション強さ: `0.0`〜`1.0`（初期値 `0.9`）
- コンプレッサー: ON/OFF、閾値、比率、アタック/リリース、メイクアップに対応

現在のUIは初心者向けに、各機能を **ON/OFF + 強さ（弱/中/強）** で操作できます。

- ノイズカット(ゲート)
- 低音ノイズカット(HPF)
- ノイズリダクション
- 声の聞き取り補正(コンプレッサー)

`pedalboard` が利用可能な環境では、ゲート/HPF/コンプレッサーに `pedalboard` エンジンを優先使用します。

```powershell
python -m pip install pedalboard
```

ホワイトノイズが残る場合は、まず次の順で調整すると安定しやすいです。

1. HPF を有効化（80〜120 Hz）
2. ノイズリダクション強さを `0.85`〜`1.0` で調整
3. ゲート閾値を `-50`〜`-35` dB 目安で調整
4. コンプレッサーのメイクアップを上げすぎない（ノイズ再増幅を防ぐ）

---

## 開発時の ffmpeg 取り扱い（同梱の手順）

このプロジェクトではリポジトリに ffmpeg バイナリを含めません。開発中や配布ビルドで mp3 出力を有効にするため、ビルド時に ffmpeg をダウンロードして同梱する仕組みを用意しています。

推奨ワークフロー:

- 自動化（推奨）: リポジトリルートで `python build_dist.py` を実行すると、`build/ffmpeg` に ffmpeg をダウンロードして展開し、PyInstaller を呼び出して ffmpeg をビルド成果物に同梱します。

	実行例:

	```powershell
	python build_dist.py
	```

- 手動（開発用）: 既に ffmpeg を入手している場合は、プロジェクト内の `build/ffmpeg/bin/` に `ffmpeg.exe` を配置してください（Windows）。スクリプトは `build/ffmpeg/bin` にある ffmpeg を検出します。

	- ダウンロード先の一例（Windows）: https://www.gyan.dev/ffmpeg/builds/
	- ZIP を展開し、中の `ffmpeg.exe` を `build/ffmpeg/bin/` にコピーします。

代替: システム全体の PATH に `ffmpeg` が含まれていれば、何も配置する必要はありません。

注意点:

- ビルドスクリプトはインターネット接続を必要とします（自動ダウンロード時）。
- `ffmpeg` の配布ライセンスを確認の上で利用してください。
- リポジトリにバイナリを含めないため、`build/ffmpeg` を `.gitignore` に追加することを推奨します（まだ `.gitignore` を使っていない場合は、任意で追加してください）。

問題があれば手順を調整しますので教えてください。
