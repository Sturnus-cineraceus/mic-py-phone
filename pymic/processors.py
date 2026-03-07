from typing import Optional
import logging

# Processor ベースクラス
# - 各種オーディオ処理ユニットの共通機能を提供する。
# - サンプルレート、チャネル数、任意のパラメータを保持し、
#   `set_params` で柔軟にパラメータ更新できるようにする。
class Processor:
    def __init__(self, samplerate: int = 44100, channels: int = 1, **params):
        """プロセッサの基底クラスを初期化する。

        Args:
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。
            **params: サブクラス固有の追加パラメータ。
        """
        self.samplerate = samplerate
        self.channels = channels
        # 処理ごとの追加パラメータを辞書で保持
        self.params = params

    def set_params(self, **params) -> None:
        """
        パラメータ更新用メソッド。
        - 呼び出されると logger.debug で変更内容を出力し、内部の `params` を更新する。
        - 個別のサブクラスは必要に応じて上書きし、親の `set_params` を呼ぶ。
        """
        logger = logging.getLogger(__name__)
        for k, v in params.items():
            logger.debug("Processor %s set param %s=%s", self.__class__.__name__, k, v)
        self.params.update(params)

    def process(self, frames):
        """
        デフォルトの処理メソッド（何もしない）。
        - `frames` はブロック（フレーム数 × チャネル数）の numpy 配列を想定。
        - サブクラスでオーバーライドして音声処理を実装する。
        """
        return frames


# Gate（ゲート）処理
# - フレーム毎の RMS レベルがしきい値未満のチャンクをミュートする。
class GateProcessor(Processor):
    def __init__(self, samplerate=44100, channels=1, threshold: float = -40.0, **params):
        """ゲートプロセッサを初期化する。

        Args:
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。
            threshold: ゲート閾値（dB）。
        """
        super().__init__(samplerate, channels, **params)
        # threshold はデシベル（dB）で指定。-40dB など。
        self.threshold = threshold
        """
        ゲートのしきい値を更新する。
        - `threshold` が None でなければ内部値を更新し、残りは親に委譲する。
        """
        if threshold is not None:
            self.threshold = threshold
        super().set_params(**params)

    def process(self, frames):
        """
        - 入力ブロックごとにチャネル分の RMS を計算し、
          デシベル換算した閾値と比較してミュートするブロックを決定する。
        - ミュートされたブロックが存在する場合は警告ログを出す。
        """
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            # フレーム単位で RMS を計算（各フレームは複数チャンネルを持つ）
            rms = np.sqrt(np.mean(np.square(f.astype(np.float64)), axis=1))
            # dB -> 線形振幅に変換
            thr_lin = 10.0 ** (self.threshold / 20.0)
            # 各フレームがしきい値以上かどうかのマスク
            mask = rms >= thr_lin
            out = f.copy()
            # マスクが False のフレームをゼロにする（ミュート）
            out[~mask, :] = 0
            if np.max(np.abs(out)) == 0:
                logging.getLogger(__name__).warning(
                    "GateProcessor: block fully muted (threshold=%s)", self.threshold
                )
            return out
        except Exception:
            # 何らかのエラーが発生した場合は入力をそのまま返す（フォールバック）
            return frames


# 単純なハイパスフィルタ（1次差分形）
# - ブロック間でフィルタ状態（過去の入力・出力）を保持し、連続した信号に対して
#   安定したフィルタリングを行う。
class HighpassProcessor(Processor):
    def __init__(self, samplerate=44100, channels=1, cutoff: float = 80.0, **params):
        """ハイパスフィルタプロセッサを初期化する。

        Args:
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。
            cutoff: カットオフ周波数（Hz）。
        """
        super().__init__(samplerate, channels, **params)
        # カットオフ周波数（Hz）
        self.cutoff = cutoff
        # ブロック間で保持する前回の入力・出力（チャネル分）
        import numpy as _np

        self._x_prev = _np.zeros((self.channels,), dtype=_np.float32)
        self._y_prev = _np.zeros((self.channels,), dtype=_np.float32)

    def set_params(self, cutoff: Optional[float] = None, **params):
        """
        ハイパスのカットオフ周波数を更新する。
        - カットオフは最低 1Hz、最大はナイキスト周波数未満に制限される。
        """
        if cutoff is not None:
            self.cutoff = cutoff
        super().set_params(**params)

    def process(self, frames):
        """
        - ブロック内の各フレームに対して 1 次ハイパス差分フィルタを適用する。
        - フィルタ係数 alpha をサンプルレートとカットオフから計算し、
          直前サンプル（_x_prev）と直前出力（_y_prev）を使って逐次処理する。
        - 出力が極端に小さい場合は警告ログを出す（異常検知用）。
        """
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            fs = float(self.samplerate)
            # カットオフは 1Hz 以上、ナイキスト未満に制限
            f0 = max(1.0, min(self.cutoff, fs / 2.0 - 1.0))
            omega = 2.0 * 3.141592653589793 * f0
            # シンプルな 1 次フィルタの係数（実務では biquad を推奨）
            alpha = fs / (fs + omega)
            out = np.zeros_like(f)
            x_prev = self._x_prev
            y_prev = self._y_prev
            # フレーム単位で差分計算を行い、状態を更新する
            for i in range(f.shape[0]):
                x = f[i, :]
                y = alpha * (y_prev + x - x_prev)
                out[i, :] = y
                x_prev = x.copy()
                y_prev = y.copy()
            # 状態を保存して次ブロックへ持ち越す
            self._x_prev = x_prev
            self._y_prev = y_prev
            if np.max(np.abs(out)) < 1e-7:
                logging.getLogger(__name__).warning(
                    "HighpassProcessor: output near-zero for cutoff=%s (samplerate=%s)",
                    self.cutoff,
                    self.samplerate,
                )
            return out
        except Exception:
            return frames


# シンプルなコンプレッサー処理
# - 各フレームの実効値（RMS）をデシベル換算し、閾値を超える部分に対して比率に応じた
#   ゲイン低下を適用する（ソフトコンプレッション）。
class CompressorProcessor(Processor):
    def __init__(
        self,
        samplerate=44100,
        channels=1,
        ratio: float = 2.0,
        threshold: float = -20.0,
        **params,
    ):
        """コンプレッサープロセッサを初期化する。

        Args:
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。
            ratio: 圧縮比（1.0 は無効）。
            threshold: 圧縮開始閾値（dB）。
        """
        super().__init__(samplerate, channels, **params)
        # ratio: 圧縮比（1.0 は無効）
        self.ratio = ratio
        # threshold: dB 単位のしきい値
        self.threshold = threshold
        """
        コンプレッサーの比率（ratio）および閾値（threshold）を更新する。
        """
        if ratio is not None:
            self.ratio = ratio
        if threshold is not None:
            self.threshold = threshold
        super().set_params(**params)

    def process(self, frames):
        """
        - 各フレームの RMS を計算し、dB が閾値を超える場合に圧縮を適用する。
        - 圧縮は dB 単位で計算し、適用するゲインを線形スケールに変換して掛ける。
        """
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            out = np.empty_like(f)
            thr = float(self.threshold)
            ratio = float(max(1.0, self.ratio))
            for i in range(f.shape[0]):
                s = f[i, :]
                level = float(np.sqrt(np.mean(np.square(s.astype(np.float64)))))
                db = 20.0 * np.log10(level + 1e-12)
                if db > thr:
                    exceed = db - thr
                    reduced_db = thr + exceed / ratio
                    gain_db = reduced_db - db
                    gain = 10.0 ** (gain_db / 20.0)
                else:
                    gain = 1.0
                out[i, :] = s * gain
            return out
        except Exception:
            return frames


# ノイズ低減（簡易 LPF による「デヒス」）
# - 強さに応じて低域を滑らかにし、環境ノイズの成分を抑える試みを行う。
# - 出力振幅が非常に小さい場合はフロア値を掛けて極端なゼロ化を避ける。
class DeHissProcessor(Processor):
    def __init__(self, samplerate=44100, channels=1, strength: float = 0.5, **params):
        """デヒス（簡易ノイズ低減）プロセッサを初期化する。

        Args:
            samplerate: サンプルレート（Hz）。
            channels: チャンネル数。
            strength: ノイズ低減の強さ（0.0〜1.0）。
        """
        super().__init__(samplerate, channels, **params)
        # strength: 0.0-1.0 の範囲で強さを指定（大きいほど強く低域を通す）
        self.strength = strength
        """
        ノイズ低減強度を更新する。
        """
        if strength is not None:
            self.strength = strength
        super().set_params(**params)

    def process(self, frames):
        """
        - 単純な一次ローパスを用いて入力を平滑化し、ノイズ成分を低減する。
        - 強さに応じてカットオフを計算し、逐次フィルタリングを行う。
        - 出力レベルが極端に低い場合は一定のフロアを乗算してゼロ化を避ける。
        """
        try:
            import numpy as np

            f = np.asarray(frames, dtype=np.float32)
            if f.size == 0:
                return f
            fs = float(self.samplerate)
            cutoff = max(100.0, min(12000.0, 1000.0 * float(self.strength)))
            alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / fs)
            out = np.empty_like(f)
            prev = np.zeros((self.channels,), dtype=np.float32)
            for i in range(f.shape[0]):
                x = f[i, :]
                y = prev + alpha * (x - prev)
                out[i, :] = y
                prev = y
            if np.max(np.abs(out)) < 1e-7:
                logging.getLogger(__name__).debug(
                    "DeHissProcessor: output near-zero after LPF (strength=%s)", self.strength
                )
            env = np.sqrt(np.mean(np.square(out.astype(np.float64))))
            floor = max(0.15, 1.0 - 0.9 * float(self.strength))
            if env < 1e-6:
                return out * floor
            return out * 1.0
        except Exception:
            return frames
