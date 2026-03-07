"""pymic パッケージ。

マイク入力にリアルタイムでオーディオ処理を施してスピーカーへ出力する
バイパスアプリケーションのエントリポイントと公開 API を提供する。
"""

from .app import main
from .api import Api

__all__ = ["main", "Api"]
