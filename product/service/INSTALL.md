# 설치 안내

이 앱은 늘 켜져 있는 컴퓨터 하나(서버 또는 늘 켜 둔 PC)에서 돌아요. 화면은 그 컴퓨터 안(127.0.0.1)과 내 Tailscale에 추가한 기기에서만 열려요. 공개 인터넷에는 열지 않아요.

설치 스크립트는 `app/install/`에 있어요. 서비스 파일은 `python -m app.install`이 만들어요(`app/app/install.py`).

## 1. 서버(Ubuntu LTS)

준비: Ubuntu 22.04 · 24.04 LTS, `python3`(3.12 권장) · `python3-venv`, 화면을 직접 빌드하려면 Node.js 22 이상. 클라우드는 서울 리전을 권해요.

```bash
git clone <이 레포> && cd <레포>/product/service/app
sudo bash install/install-server.sh            # 기본: 가짜 전송(주문 · 텔레그램 · DART가 밖으로 나가지 않아요)
```

1. 서비스 사용자 `quant`, 앱 `/opt/quant-service/app`, 데이터 `/var/lib/quant-service/data`(권한 700)를 만들어요.
2. 파이썬 가상 환경 · 화면 빌드.
3. Tailscale이 없으면 설치하고 `tailscale up`으로 로그인 링크를 보여 줘요. 링크를 열어 내 계정으로 로그인해요.
4. systemd 서비스 `quant-service`를 등록하고 켜요(재부팅 뒤 자동 시작 · 꺼지면 5초 뒤 다시).
5. `tailscale serve`로 `https://<이 서버>.<내 망>.ts.net` 화면 주소를 열어요. 이 이름만 앱의 Host 검사를 통과해요(`QUANT_TS_NAME`).

화면 주소를 휴대폰 · 노트북에서 열려면 그 기기에도 Tailscale을 깔고 같은 계정으로 로그인해요.

### 실제 주문을 켜기

실제 전송은 **두 열쇠**가 다 있을 때만 열려요(`DEVELOPING.md` 3절): 설정 파일 `/etc/quant-service/live-transport.json`의 `{"live_transport": true}`와 서비스 환경 변수 `QUANT_LIVE_TRANSPORT=1`. 설치 스크립트는 `--live`를 줄 때만 둘을 써요.

```bash
sudo bash install/install-server.sh --live
```

실제 키로 처음 확인하는 일(토스 연결 확인 · 소액 주문 · 텔레그램 시험 보내기)은 사용자가 직접 해요.

## 2. 늘 켜 둔 PC(macOS)

준비: `brew install python@3.12`(화면을 직접 빌드하려면 `brew install node`).

```bash
cd <레포>/product/service/app
bash install/install-mac.sh                    # 실제 전송은 --live
```

앱 `~/quant-service/app`, 데이터 `~/quant-service/data`, launchd `~/Library/LaunchAgents/kr.quant.service.plist`(로그인할 때 자동 시작 · 꺼지면 다시). 절전 모드를 꺼 두어요. 휴대폰으로 보려면 Tailscale 앱을 깔고 `tailscale serve --bg --https=443 http://127.0.0.1:8765`를 켜요(선택). 노트북은 권하지 않아요.

## 3. 재부팅

서비스로 등록돼 있어 컴퓨터를 다시 켜면 앱이 자동으로 켜져요. 데이터 키는 그 컴퓨터의 키 파일(`~/.config/quant-service/keyfile` · 권한 600 · 레포와 데이터 폴더 밖)로 풀려서 **로그인 없이 운용이 이어져요**. 화면에 들어올 때는 비밀번호가 필요해요('컴퓨터를 다시 켰어요 · 실전 운용은 로그인 없이 계속돼요').

## 4. 업데이트 · 되돌리기(SPEC 5-10)

```bash
sudo bash install/update.sh <새 버전의 app 폴더> 1.1
```

- **거래일 16:00~20:00**(그날 20:10 확인 전)에만 해요. 그 밖이면 이유를 보이고 멈춰요.
- 순서: 스케줄러 멈춤 → 백업(`data/backups/`) → 데이터 구조 바꿈 → 다시 켬 → 대조. 단계는 `data/update.json`에 적혀 앱 머리 칩 '업데이트 중'으로 보이고, 끝나면 텔레그램 '업데이트 끝 · 버전 1.1'.
- 어느 단계든 실패하면 이전 버전 폴더와 백업 파일로 되돌리고 다시 켜요.

## 5. 지우기

```bash
sudo bash install/uninstall.sh           # 앱 · 서비스만
sudo bash install/uninstall.sh --purge   # 데이터 · 키 파일까지
```

## 6. 확인한 것 · 남은 확인

- 개발 컨테이너(Ubuntu 24.04 · systemd가 PID 1이 아님)에서: 서비스 파일 · plist 꼴, 업데이트 시간 규칙, 단계 기록, 스크립트 문법, 서비스 명령 그대로 켜기 → 끄기 → 다시 켜기(키 파일로 로그인 없이 이어짐)를 시험했어요(`tests/test_install.py`). 가짜 키 · 가짜 전송 · 오프라인.
- 깨끗한 Ubuntu LTS · macOS에 실제로 설치하고 컴퓨터를 다시 켜는 확인, 실제 키를 넣는 확인은 사용자가 해요(`OPEN-QUESTIONS.md` Q-N11).
