"""API 층(ARCHITECTURE 2절): 기능별 라우터 · 화면이 받는 모양.

기능별 라우터(P1-09 · 옮기기 전 `main.py` · `api_v2.py`): `account`(처음 열기 · 로그인 · 계정) · `connect`(토스 · DART 키) ·
`access`(접속) · `live`(실전 운용 · 할 일 처리 · 화면 모양) · `data`(백업 · 복원 · 삭제 · CSV · 업데이트) · `telegram` ·
`paper`(모의투자 v2) · `strategies`(v2 전략 · 백테스트) · `web`(화면 파일 · 맨 끝). 같이 쓰는 것: `http`(오류 응답 · 몸통 ·
쿠키) · `guard`(바깥 문 미들웨어) · `errors`(오류 → HTTP). 등록은 조립(`app.py`)이 해요.
가져와도 되는 것: `services` · `run` · `store`(읽기 쿼리) · `domain` · `security` · `copy`(어댑터 직접 · SQL은 안 됨).
"""
