# AI実行ルール（プロジェクト向け）

目的: このファイルは、AI（または自動化エージェント）がこのリポジトリ内でコマンドや検査を実行する際の明確な手順とルールを示します。

基本原則
- ユーザーが仮想環境（venv）で作業していると言った場合、必ずその venv の Python 実行ファイルを使ってコマンドを実行する。
- コマンドがシステム PATH にない場合でも、`python -m <module>` 形式で実行してモジュールを呼び出す。
- 実行前にユーザーの許可が必要なら必ず確認する。明示的な許可がある場合のみ実行する。

Windows (PowerShell) の推奨ワンライナー
- venv にある Python を直接呼び出す（推奨）:
  - `.\venv\Scripts\python.exe -m ruff check --fix .`
  - `.\venv\Scripts\python.exe -m py_compile pymic/api.py`
  - `.\venv\Scripts\python.exe .\main.py`
- モジュール呼び出しの代替（PATH に ruff が無い場合）:
  - `python -m ruff check --fix .`  （ただし `python` が venv のものを参照している前提）

Unix/macOS の推奨ワンライナー（参考）
- `./venv/bin/python -m ruff check --fix .`
- `./venv/bin/python -m py_compile pymic/api.py`

実行ポリシー
- 変更を加えたら、少なくとも次を実行して確認する：
  1. 文法チェック: `python -m py_compile <file>`
  2. リント/自動修正: `python -m ruff check --fix .`（ruff が venv にインストール済みの場合は venv の python で実行）
  3. 必要ならアプリ起動で動作確認: `.\venv\Scripts\python.exe .\main.py`
- 長時間かかる操作（依存インストールや大規模テスト）は事前に通知する。

エラー時の取り扱い
- 実行が失敗したら、標準出力・標準エラーの抜粋（重要な部分）を返し、続けて何を試すか提案する。
- コマンドが見つからない場合は、`python -m <module>` を試し、次に venv の Python 実行ファイルを明示的に使うワンライナーを提案する。

開発者向けメモ
- このファイルは人と AI の両方が参照することを想定しています。変更する場合はコミットして履歴を残してください。

---
作業例（PowerShell コピー用）:

```powershell
# Lint を venv の Python で実行
.\venv\Scripts\python.exe -m ruff check --fix .

# 単一ファイルの文法チェック
.\venv\Scripts\python.exe -m py_compile pymic/api.py

# 直接 venv の Python を指定して単一ファイルを文法チェックするワンライナー（推奨）
.\venv\Scripts\python.exe -m py_compile pymic/api.py

# アプリ実行
.\venv\Scripts\python.exe .\main.py
```
