// Old words from product/service/GLOSSARY.md §4 · §5 (words the screens must not show), plus
// '전략 코드' (brief: 디자인 고치기 1회 뒤). Regexes skip the allowed uses the terms table and the
// designs keep: 빈칸 · 숫자 칸 (입력 상자 뜻), 붙여 넣기 (화면 이름), 투자 판단 (약관), 틀리다 (동사).
export const OLD_WORDS: readonly RegExp[] = [
  /주인/,
  /입장/,
  /들어가기|들어오기|들어올 수/,
  /마법사/,
  /콘솔/,
  /일회용 표/,
  /봉인 키/,
  /견주기|견줘요/,
  /휴대폰 붙이|휴대폰을 붙여/,
  /산 글/,
  /되살리기/,
  /토스 키/,
  /키 바꾸기|키 다시 넣기|키 넣기/,
  /키 묶음/,
  /자료/,
  /바깥 감시/,
  /감시 서비스/,
  /닿지 않아요|닿지/,
  /(?<!빈)(?<!숫자 )칸(?!\s?[ 이]?[가-힣]*입력)/,
  /일곱 칸/,
  /조각/,
  /빈 틀/,
  /틀(?![리린려렸])/,
  /사고팔|사고판/,
  /사건형/,
  /(?<![가-힣])꼴/,
  /처음 진입|처음 참이/,
  /참인 날|참이던/,
  /깨짐/,
  /정보원/,
  /그리고 · 또는/,
  /묶음|묶기/,
  /시장 스위치/,
  /순위 밖/,
  /지킬 순위/,
  /맡기기|맡겨/,
  /복사 글/,
  /이음/,
  /(?<!투자 )판단/,
  /저절로/,
  /도는 중|(?<!되)돌아요|도는 실행|(?<!되)돌리기|(?<!되)돌릴/,
  /실행기/,
  /감시 가격/,
  /새 매수/,
  /멈춤|멈추기|멈춰요|멈췄/,
  /걷으려면/,
  /나누지 않은|나눈 돈|나눌까요/,
  /안 산 신호/,
  /셈했어요/,
  /권함/,
  /총 수익률/,
  /매매 횟수/,
  /비용 뺀/,
  /낸 비용/,
  /시도한 수/,
  /균등/,
  /다시 맞추기/,
  /고치기|고칠 곳/,
  /지우기/,
  /바꾸기/,
  /(?<!붙여 )넣기|값 넣기|넣어 주세요/,
  /모양이 맞지/,
  /에서 멈춤/,
  /잠김/,
  /다시 돌아요/,
  /낡음/,
  /시험 알림/,
  /전략 코드/,
  // 검토 지적 9 · 10(GLOSSARY 4절: 고치기 · 지우기 · 순위 이탈)
  /고쳐|고칠/,
  /지워|지웠/,
  /순위 안/,
  /신호 밖/,
];

/** Every old word found in `text` with a little context. */
export function oldWordHits(text: string): string[] {
  const hits: string[] = [];
  for (const re of OLD_WORDS) {
    const g = new RegExp(re.source, 'g');
    for (const m of text.matchAll(g)) {
      const at = m.index;
      hits.push(`${re.source}: …${text.slice(Math.max(0, at - 12), at + 12)}…`);
    }
  }
  return hits;
}
