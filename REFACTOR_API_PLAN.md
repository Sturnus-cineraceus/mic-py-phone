## REFACTOR — API とパイプラインのオブジェクト指向再設計

目的: `Api` を外部向けの薄いファサードにし、録音・バイパス（パイプライン）・トランスクリプション・デバイス・Sink を明確なインターフェースとして切り出す。中心は `Pipeline` で、エフェクトチェーンと出力（sinks）を管理する。

概要:
- 現状: `pymic/api.py` に GUI API、リアルタイム処理、設定管理、sink 登録など多くの責務が集中している。
- 改善方針: 責務分離 (SRP)、依存注入、リアルタイム callback を短く保つ（I/O は必ず別ワーカへ）。

推奨インターフェース（概要）
- `DeviceManager` / `Device`
  - 責務: デバイス列挙 / 選択 / ストリーム生成ラッパ。
  - 主なメソッド: `list_input_devices()`, `list_output_devices()`, `create_stream(config)`
- `Pipeline`
  - 責務: リアルタイム音声処理（エフェクトチェーン適用・設定スナップショット管理・入力→出力・sink への dispatch）。
  - 主なメソッド: `start(config)`, `stop()`, `apply_settings(settings_snapshot)`, `process_frame(frames)->frames`, `get_levels()`
- `Sink` (抽象)
  - 責務: フレームを受け取り処理する。I/O や外部呼び出しは内部で非同期化する。
  - メソッド: `consume(frames: np.ndarray, meta: dict)`
- `SinkManager`
  - 責務: Sink 登録/解除、配送、バックプレッシャ/ポリシー管理、メトリクス。
  - メソッド: `register_sink(sink, policy)`, `unregister_sink(id)`, `dispatch(frames)`
- `Recorder` / `RecorderSink`
  - 責務: 録音データの永続化（WAV→変換）。FFmpeg 呼び出し等の重い処理は別ワーカ/プロセスで実行。
  - メソッド: `start()`, `stop()`, `consume(...)`
- `Transcriber` / `TranscribeSink`
  - 責務: VAD による区間抽出 → 非同期 ASR 呼び出し → 結果コールバック。
- `SettingsStore`/`SettingsManager`
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
- `Api` の多責務：テスト難、変更時のリスク増大。
- Sink の暗黙契約：メタデータや状態管理が不十分。
- 重い同期 I/O のワーカ化が未実装：callback の応答性を損なう危険。
- 設定の race 条件：更新時の整合性が必要。

提案する検証フロー
1. ユニットテスト: 各 `Processor.process()` に対する小さな numpy 入力テスト。
2. 統合テスト: `Api` → `Pipeline` → `Sink` のモックを使ったフロー検証。
3. 負荷テスト: 重い sink を登録して dispatch の挙動を測る。

マイグレーション方針
- 段階的に移行し、`Api` 互換の thin adapter を残すことで UI 側への影響を最小化する。

作業候補（次のアクション、選択してください）
- A: `Api` の分割と `Pipeline` の骨組み実装（推奨初手）
- B: `Sink` インターフェース導入と `SinkManager` の改良
- C: `Recorder` の非同期化（ffmpeg 呼び出しを別ワーカへ）
- D: フロントのポーリング→プッシュ化

---

ファイルを更新しました。次はどれを実装しますか？（A/B/C/D のいずれか、または優先順を指示してください。）
