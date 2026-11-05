"""실행 흐름(ARCHITECTURE 2절 실행 흐름 층 · TASKS P1-08).

- `data.py`: 읽어 오며 저장하기(일봉 캐시 판단 · `MarketFeed` 포트로 받기 · `store/market.py`에 저장 · 장 달력).
- `scheduler.py`: 일 시각 표 하나와 스케줄러(하루 한 번 일 · 실패하면 10분 뒤 다시).
- `live.py`: 실전 운용 흐름 · 실전 상태의 주인(`Live` · 사용자 실전 조작 12개는 주인의 공개 메서드 · 앱 루프의 `tick`).
- `paper.py`: 모의투자 v2(20:10 확인 · 다음 거래일 일봉 시가 체결).
- 가져와도 되는 것: `domain` · `orders` · `ports` · `store` · `copy`(어댑터 구현 · fastapi는 안 됨 · 조립이 넣어 줌).
"""
