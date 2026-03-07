"""pymic パッケージの公開インターフェース。

`main` 関数と `Api` クラスをパッケージ外部に公開する。
"""

from .app import main
from .api import Api

__all__ = ["main", "Api"]
