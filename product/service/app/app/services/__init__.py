"""쓰기 일(ARCHITECTURE 2절 쓰기 일 층 · TASKS P1-09): 사용자가 바꾸는 일을 검사 → 저장 → 기록 한 곳에서.

- `updates.py`: 업데이트 상태 · `update.json` 꼴(읽기 · 설치기 쓰기) · 끝 알림.
- `data_admin.py`: 백업 · 복원 · 앱 데이터 삭제 · 기록 CSV · 현황(저장 부분은 `store/data_admin.py`).
- `connect.py`: 토스 · DART 키 저장과 토스 연결 확인(증권사는 `Broker` 포트 · 클라이언트는 조립이 만들어 줌).
- `telegram.py`: 텔레그램 설정 · 알림 · 보내기 · 본문 · `telegram_commands.py`: `/상태` · `/멈춤` 받기(이어받아 더함).
- `access.py`: 설치 위치 고르기 · 접속 보기 · `strategies.py`: 전략 저장 · 새 버전 · 지우기 · 백테스트 기록.
- 실전 운용 조작은 여기가 아니라 실행 흐름의 주인(`run/live.py`)의 공개 메서드예요.
- 가져와도 되는 것: `domain` · `orders` · `store` · `ports` · `security` · `copy`(fastapi · 어댑터 구현은 안 됨 · 조립이 넣어 줌).
"""
