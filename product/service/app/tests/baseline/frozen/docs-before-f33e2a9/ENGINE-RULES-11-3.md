<!-- product/service/ENGINE-RULES.md · f33e2a9^ 판 · 이 부분만 · P1-01a가 떼어 둠(Q-N18) -->

### 11-3. 항목 id 사전

v1의 조건 id 15개는 v3에서도 받아요. 그 가운데 9개(`manual_list` · `top_n` · `next_open` · `stop_loss` · `take_profit` · `max_hold` · `equal` · `max_per_stock` · `rebalance_every`)는 v3 항목 id로 그대로 이어 쓰고, 6개는 읽을 때 '별칭' 열대로 바꿔요(R-C8). v3 글을 쓸 때는 이 표의 id만 써요. 강도 열은 R-M3 표예요.

| id | 이름 | op | params 키 | value · 단위 | 블록 | 강도 | 별칭(v1 id) |
|---|---|---|---|---|---|---|---|
| `manual_list` | 종목 직접 지정 | pick | — | 종목 코드 배열(1~30) | ① | — | manual_list |
| `market` | 시장 | pick | — | `["KOSPI","KOSDAQ"]` 가운데 | ① | — | |
| `security_type` | 종목 유형 | pick | — | `stock` · `etf` · `etn` · `reit` 배열 | ① | — | |
| `exclude_preferred` | 우선주 제외 | exclude | — | null | ① | — | |
| `exclude_leveraged` | 레버리지 · 인버스 ETF 제외 | exclude | — | null | ① | — | |
| `listed_days` | 상장 기간 | gte | — | 일 | ① ③ | 없음 | |
| `sector` | 섹터 | pick · exclude | `level`(`large` · `mid` · `small`) | 토스 섹터 id 배열 | ① ③ | 없음 | |
| `exclude_warning` | 거래정지 · 정리매매 · 투자경고 · 투자위험 제외 | exclude | — | null | ① | — | |
| `price` | 주가 | gte · lte · between | — | 원 | ② ③ ⑥ | 없음 | min_price(gte) |
| `change_pct` | 등락률(전일 대비) | gte · lte | — | % | ② ③ ⑥ | 없음 | |
| `return_n` | n일 수익률 | gte · lte · top_pct · bottom_pct | `n`(1~250) | %(순위면 %) | ② ③ ⑥ · ④ | gte만 있음 | |
| `high_n` | n일 최고가(신고가) | cross_up | `n`(5~250) | null | ② | 있음 | high_breakout |
| `from_52w_high` | 52주 최고가 대비 | gte · lte | — | % | ② ③ ⑥ | 없음 | |
| `low_n` | n일 최저가(신저가) | cross_down | `n`(5~250) | null | ② ⑥ | 있음 | |
| `gap` | 시가 갭 | gte | `dir`(`up` · `down`) | % | ② ⑥ | 없음 | |
| `volume` | 거래량 | gte · lte | — | 주 | ② ③ | 없음 | |
| `turnover` | 거래대금 | gte · lte · top_n | — | 억 원(순위면 개수) | ② ③ · ④ | 없음 | min_turnover(gte) |
| `volume_ratio` | 거래량 비율(n일 평균 대비) | gte · lte | `n`(2~250) | % | ② ③ | 없음 | |
| `volatility` | 변동성(n일) | gte · lte · bottom_pct | `n`(5~250) | % | ③ · ④ | 없음 | |
| `ma` | 이동평균선 | cross_up · cross_down · above · below | `n`(2~250) | null | ② ③ ⑥ | 있음 | ma_cross_up(cross_up) · ma_break_down(below) |
| `ema` | 지수이동평균선 | cross_up · cross_down · above · below | `n`(2~250) | null | ② ③ ⑥ | 있음 | |
| `ma_cross` | 이동평균선 교차 | cross_up(골든) · cross_down(데드) | `short` · `long`(2~250) | null | ② ⑥ | 있음 | |
| `ma_align` | 이동평균선 배열 | aligned_up · aligned_down | `n1` · `n2` · `n3`(2~250) | null | ② ③ ⑥ | 없음 | |
| `disparity` | 이격도 | gte · lte | `n`(2~250) | %(50~200) | ② ③ ⑥ | 없음 | |
| `rsi` | RSI | gte · lte · lt · cross_up · cross_down | `period`(2~50) | 0~100 | ② ③ ⑥ | gte 빼고 있음 | rsi_below(lt · `level` → value) |
| `macd` | MACD | cross_up · cross_down | `fast` · `slow` · `signal`(2~100) · `line`(`signal` · `zero`) | null | ② ⑥ | 있음 | |
| `bollinger` | 볼린저밴드 | cross_up(상단) · cross_down(하단) | `n`(5~250) · `k`(0.5~5) | null | ② ⑥ | 있음 | |
| `streak` | 연속 상승 · 하락 | consec | `dir`(`up` · `down`) | 일(2~20) | ② ③ ⑥ | 없음 | |
| `market_cap` | 시가총액 | gte · lte · top_n · bottom_pct | — | 억 원 | ① ③ · ④ | 없음 | |
| `per` | PER(최근 4분기 합) | gte · lte · between · bottom_pct | — | 배 | ③ ⑥ · ④ | 없음 | |
| `pbr` | PBR | gte · lte · between · bottom_pct | — | 배 | ③ ⑥ · ④ | 없음 | |
| `psr` | PSR(최근 4분기 합) | gte · lte · between · bottom_pct | — | 배 | ③ ⑥ · ④ | 없음 | |
| `dividend_yield` | 배당수익률(전년 배당) | gte · lte · top_n | — | % | ③ · ④ | 없음 | |
| `roe` | ROE | gte · lte · top_pct | — | % | ③ · ④ | 없음 | |
| `op_margin` | 영업이익률 | gte · lte | — | % | ③ · ④ | 없음 | |
| `profit_state` | 흑자 · 적자 · 흑자전환 · 적자전환 | pick | `line`(`op_income` · `net_income`) | `profit` · `loss` · `turn_profit` · `turn_loss` | ② ③ ⑥ | 없음 | |
| `sales_growth` | 매출액 증가율(전년 동기 대비) | gte · lte · top_pct | — | % | ③ · ④ | 없음 | |
| `profit_growth` | 영업이익 · 순이익 증가율 | gte · lte | `line`(`op_income` · `net_income`) | % | ③ | 없음 | |
| `sales_growth_3y` | 최근 3년 평균 매출 증가율 | gte · lte | — | % | ③ | 없음 | |
| `debt_ratio` | 부채비율 | gte · lte | — | % | ③ ⑥ | 없음 | |
| `net_buy` | 외국인 · 기관 · 개인 순매수(어제까지 n일 합) | gte · lte · consec | `who`(`foreign` · `institution` · `individual`) · `n`(1~60) · `unit`(`shares` · `pct_volume`) · consec면 `side`(`buy` · `sell`) | 주 또는 % | ② ③ ⑥ | 없음 | |
| `foreign_ratio` | 외국인 지분율(어제 확정치) | gte · lte · consec(증가) | consec면 `n` | % | ③ | 없음 | |
| `disclosure` | 공시 | within_days · not_within_days | `kind`(`buyback` · `treasury_sale` · `rights_issue` · `bonus_issue` · `capital_reduction` · `cb` · `bw` · `merger` · `split` · `business_transfer` · `lawsuit` · `default` · `rehabilitation` · `dissolution` · `earnings`) | 일(1~60) | ② ③ ⑥ | 없음 | |
| `index_ma` | 코스피 · 코스닥 지수 이동평균선 | above · below · cross_up · cross_down | `index`(`KOSPI` · `KOSDAQ`) · `n`(2~250) | null | ③ ⑥ | 없음 | |
| `stop_loss` | 손절 | fixed | — | %(1~50 · 매수가보다 n% 내려가면) | ⑥ | — | stop_loss(`pct` → value) |
| `take_profit` | 익절 | fixed | — | %(1~500) | ⑥ | — | take_profit(`pct` → value) |
| `trailing_stop` | 트레일링 스톱 | fixed | — | %(1~50 · 매수 뒤 최고가보다) | ⑥ | — | |
| `max_hold` | 최대 보유 | fixed | — | 거래일(1~250) | ⑥ | — | max_hold(`n` → value) |
| `next_open` | 다음 날 시가 매수 · 판 뒤 다시 사지 않는 기간 | fixed | — | 거래일(0~20) | ⑤ | — | next_open(값 0) |
| `top_n` | 정렬 | top_n | `by`(`strength` · `return_n` · `turnover` · `market_cap` · `per` · `pbr` · `psr` · `dividend_yield` · `roe` · `op_margin` · `sales_growth` · `volatility`) · `order`(`desc` · `asc`) · by가 return_n · volatility면 `n` | 종목(1~30) | ④ | — | top_n(by = strength · desc · `n` → value) |
| `equal` | 동일 비중 | fixed | — | null | ⑦ | — | equal |
| `max_per_stock` | 종목당 최대 비중 | fixed | — | %(1~100) | ⑦ | — | max_per_stock(`pct` → value) |
| `rebalance_every` | 리밸런싱 주기 | fixed | `how`(`target` · `rank` · 고르기 값이라 비우지 않음) | 거래일(1~250) | ⑦ | — | rebalance_every(`n` → value) |

- 값 범위 · 단위는 `DATA-CATALOG.md` 1절과 같아요(다르면 SPEC 4-9가 이겨요).
- 사전에 항목을 더하면 앱 버전을 올리고(`app>=`), 그 항목을 쓴 글은 낮은 앱이 R-C4로 거절해요.
