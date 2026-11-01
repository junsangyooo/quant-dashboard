# vendor · 바깥 API의 응답 꼴

가짜 응답(시험 · `MVP_TOSS_OFFLINE` · 기본 가짜 전송)을 만들 때 따르는 **꼴의 근거**예요. 앱은 이 파일들을 실행 중에 읽지 않아요. 가짜 응답은 이 꼴을 따르고, 값은 지어내요.

| 파일 | 무엇 | 출처 | 받은 날 |
|---|---|---|---|
| `toss-openapi-1.2.28.json` | 토스증권 Open API 명세(OpenAPI 3.1.0 · `info.version` 1.2.28 · 경로 39개) | https://openapi.tossinvest.com/openapi-docs/latest/openapi.json (공개 문서 · 받기만 했고 API는 부르지 않았어요) | 2026-11-02 |
| `dart-samples/*.json` · `CORPCODE.sample.xml` | DART OpenAPI 응답 견본 | 공개 개발 가이드(https://opendart.fss.or.kr/guide/main.do)의 필드 이름을 보고 **값은 지어냈어요**. 실제 응답과 필드가 다르면 개발 때 고쳐요 | 2026-11-02 작성 |

- `toss-openapi-1.2.28.json`의 SHA-256: `18fdc96fdf632e4869c765ed0cb169049c5310a1c48e10b40e47a71f52aa7a45`. 토스가 `latest`를 바꾸면 그때 받은 파일을 새 이름(`toss-openapi-<버전>.json`)으로 더하고, 이 파일은 그대로 둬요.
- 이 명세 파일의 권리는 토스증권에 있어요. 공개 레포에 그대로 두어도 되는지는 `../OPEN-QUESTIONS.md` Q-L6에 적었어요.

## DART 견본

| 파일 | API | 쓰임(SPEC 11-1 순서 3) |
|---|---|---|
| `CORPCODE.sample.xml` | `corpCode.xml`(zip 안의 XML) | 종목 코드 ↔ DART 고유번호 |
| `list.json` | `list.json` | 공시 목록 · 접수일(`rcept_dt`) |
| `fnlttMultiAcnt.json` | `fnlttMultiAcnt.json` | 재무 주요계정(연결 `CFS` 우선) |
| `stockTotqySttus.json` | `stockTotqySttus.json` | 주식 총수(시가총액 · PER 계산) |
| `alotMatter.json` | `alotMatter.json` | 배당(행 이름 `se`는 확인 전 · Q-T5) |
| `tsstkAqDecsn.json` | 주요사항보고서 '자기주식 취득 결정' | 이벤트 줄의 한 예 |
| `error-limit.json` · `error-nodata.json` · `error-key.json` | 오류 응답(`status` 020 · 013 · 010) | 하루 20,000건 넘음 · 자료 없음 · 키 오류 |
