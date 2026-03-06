## Progress / TODO

この文書は進捗追跡用の TODO リストとして使います。作業は小さなステップに分割し、完了したらここに反映します。現在の TODO はリポジトリの `manage_todo_list` と同期されています。
1. Api をファサード化し Pipeline を注入する — in-progress
2. `pymic/pipeline.py` に `BypassPipeline` 骨組みを実装 — not-started
3. `pymic/processors.py` に各 Processor クラス（Gate/HPF/Compressor/DeHiss/NR）を実装 — not-started
10. ドキュメント更新: `REFACTOR_API_PLAN.md` に進捗を記録 — not-started
3) `Recorder` 非同期化（中優先）
  - I/O / ffmpeg 呼び出しをワーカへ分離し、callback 側はキュー投入のみ。現状 `Recorder` は callable sink として動作します（互換性維持）。
## REFACTOR — API とパイプラインのオブジェクト指向再設計

目的: `Api` を外部向けの薄いファサードにし、録音・バイパス（パイプライン）・トランスクリプション・デバイス・Sink を明確なインターフェースとして切り出す。中心は `Pipeline` で、エフェクトチェーンと出力（sinks）を管理する。

概要:

推奨インターフェース（概要）
  - 責務: デバイス列挙 / 選択 / ストリーム生成ラッパ。
  - 主なメソッド: `list_input_devices()`, `list_output_devices()`, `create_stream(config)`
  - 責務: リアルタイム音声処理（エフェクトチェーン適用・設定スナップショット管理・入力→出力・sink への dispatch）。
  - 主なメソッド: `start(config)`, `stop()`, `apply_settings(settings_snapshot)`, `process_frame(frames)->frames`, `get_levels()`
  - 責務: フレームを受け取り処理する。I/O や外部呼び出しは内部で非同期化する。
  - メソッド: `consume(frames: np.ndarray, meta: dict)`
  - 責務: Sink 登録/解除、配送、バックプレッシャ/ポリシー管理、メトリクス。
  - メソッド: `register_sink(sink, policy)`, `unregister_sink(id)`, `dispatch(frames)`
  - 責務: 録音データの永続化（WAV→変換）。FFmpeg 呼び出し等の重い処理は別ワーカ/プロセスで実行。
  - メソッド: `start()`, `stop()`, `consume(...)`
  - 責務: VAD による区間抽出 → 非同期 ASR 呼び出し → 結果コールバック。
  - 責務: 設定のロード/保存/バリデーション。UI はここを経由して編集する。

短期実装計画（優先度付き）
1) `Api` のファサード化（高優先）
   - `Api` は UI とコンポーネントのブリッジに限定。内部で `Pipeline`, `DeviceManager`, `SinkManager` を注入・管理する。
2) `Sink` 抽象化 + `SinkManager` 改良（中優先）
   - `Sink` インターフェース導入。`SinkManager` にキュー/ドロップポリシー/メトリクスを追加。
3) `Recorder` 非同期化（中優先）
   - I/O / ffmpeg 呼び出しをワーカへ分離し、callback 側はキュー投入のみ。
4) `Pipeline` の設計/実装（高優先）
   - `pymic/pipeline.py` または `pymic/processors.py` に `BypassPipeline` を実装。プロセッサ群（Gate/HPF/Comp/DeHiss/NR）は個別クラスとして提供。
5) 設定の不変スナップショット化（高優先）
   - callback 内で参照する設定はイミュータブルなスナップショットとして差し替える。
6) UI の改善（低〜中優先）
   - レベル表示をポーリングからイベントプッシュへ変更すると効率的。

設計上の懸念点（現状から修正すべき点）

提案する検証フロー
1. ユニットテスト: 各 `Processor.process()` に対する小さな numpy 入力テスト。
2. 統合テスト: `Api` → `Pipeline` → `Sink` のモックを使ったフロー検証。
3. 負荷テスト: 重い sink を登録して dispatch の挙動を測る。

マイグレーション方針

作業候補（次のアクション、選択してください）


ファイルを更新しました。次はどれを実装しますか？（A/B/C/D のいずれか、または優先順を指示してください。）

## Progress / TODO

この文書は進捗追跡用の TODO リストとして使います。作業は小さなステップに分割し、完了したらここに反映します。現在の TODO は `manage_todo_list` と同期されています。

- [x] Api をファサード化し Pipeline を注入する
- [x] `pymic/pipeline.py` に `BypassPipeline` 骨組みを実装
- [x] `pymic/processors.py` に各 Processor クラス（Gate/HPF/Compressor/DeHiss/NR）を実装
- [x] `Sink` 抽象を定義し `SinkManager` を改良
- [x] `Recorder` を `RecorderSink` に移行し非同期化（ffmpeg ワーカ）
- [x] 設定のスナップショット機構を実装し Pipeline に適用
- [x] ユニットテスト: Processor 単体テストを追加
- [ ] 統合テスト: `Api`→`Pipeline`→`Sink` フローの検証
- [x] 統合テスト: `Api`→`Pipeline`→`Sink` フローの検証
- [ ] フロントエンドの必要な適応（最小限）を実施
- [x] ドキュメント更新: `REFACTOR_API_PLAN.md` に進捗を記録

変更履歴:
- `pymic/pipeline.py` に `snapshot()` と `apply_snapshot()` を追加しました。
- `tests/test_processors.py` を追加し、Processor の基本動作を検証して 4 件のテストが通りました。

次の短期作業:
- `統合テスト` を作成して `Api`→`Pipeline`→`Sink` のエンドツーエンド動作を確認します。
- 必要に応じてフロントエンドの最小調整を行います。

（自動化: 進捗は `manage_todo_list` にも反映済みです）

## Recent automated changes

- Extracted `BypassController` to manage stream/pipeline lifecycle and VAD.
- Delegated `start_bypass`, `stop_bypass`, and `set_transcribe_enabled` from `Api` to `BypassController`.
- Removed `numpy` usage from `pymic/api.py`; numerical work resides in `Recorder`, `Pipeline`, and `BypassController`.
- Ran full test suite: `20 passed`.
