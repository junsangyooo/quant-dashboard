"""v1 엔진 고정본(TASKS T-02 · SPEC 4-8 · ENGINE-RULES R-C10). 시험에서만 써요 · 고치지 않아요.

2026-11-02 커밋 39dedac의 `app/engine.py` · `app/graph.py` · `app/pieces.py` · `app/strategy.py`를
글자 하나 바꾸지 않고 복사했어요(`tests/test_engine_v1.py`가 SHA-256으로 지켜요).
그 파일들이 `from . import APP_VERSION`을 쓰므로 그때의 값을 여기에 둬요.
"""

APP_VERSION = (0, 2)
APP_VERSION_TEXT = "0.2"
