# quant-dashboard

quant.jsyoo.dev의 저장소다. 자동매매 엔진과 API(`autotrade/`), 그 화면(`web/`)이 들어 있다.

- 엔진은 규칙대로 장부를 굴리고 사건과 기록을 남긴다. 정기 작업(5분마다 도는 tick, AI 작업)은 cron이 부르고, 웹 API는 그 기록을 읽어 화면에 내준다.
- 모의 장부와 실전 장부가 있다. 실전 주문은 두 열쇠(cron 줄의 `AUTOTRADE_LIVE_ORDERS=1`과 화면에서 PIN으로 켠 '실전' 모드)가 모두 있을 때만 나간다.

## 폴더

```
autotrade/   엔진·API (Python 3.10)
  api/       FastAPI 앱, 배포 도우미(release.py)
  engine/    단계 실행·대조·스냅숏
  domain/    비중·주문 계획·금액 계산
  jobs/      cron 진입점(tick, ai, migrate, backup)
  broker/    모의 체결, 토스 실주문 클라이언트
  market/    시세·환율·공시 소스, 거래소 달력
  ai/        모델 호출(구독 CLI)과 그 일감
  db/        SQLite 스키마와 마이그레이션
web/         화면 (React + Vite)
tests/autotrade/   엔진·API·배포 파일 테스트
deploy/      deploy.sh · autotrade.service · autotrade.cron · nginx-quant.conf
             logrotate-quant · install_cron.py
```

운영 데이터는 서버의 `data/`에 있고 git에 들어가지 않는다(`autotrade.db`, 토큰 캐시, 백업, 로그).

## 테스트

```bash
# Python (서버와 같은 3.10)
python -m pytest tests/autotrade -q
ruff check --config autotrade/pyproject.toml autotrade tests/autotrade
mypy --config-file autotrade/pyproject.toml autotrade tests/autotrade

# web
cd web && npm ci && npm run lint && npm run typecheck && npm test
```

`autotrade/pyproject.toml` 머리에 의존성을 고정한 `uv run` 명령이 있다.

## 배포

노트북에서 실행한다. 서버 폴더는 `~/quant-dashboard`다.

```bash
./deploy/deploy.sh autotrade          # 웹 빌드 → 코드 이동 → DB 백업·마이그레이션 → 웹 전환 → 재시작·헬스체크
./deploy/deploy.sh                    # push와 서버 pull만 (재시작 없음)
./deploy/deploy.sh rollback [<commit>] [--yes] [--drop-live]
```

각 단계와 되돌리기 규칙은 `deploy/deploy.sh` 머리 주석에 있다. systemd·cron·nginx·logrotate 설치 방법은 각 파일 머리 주석에 있다.
