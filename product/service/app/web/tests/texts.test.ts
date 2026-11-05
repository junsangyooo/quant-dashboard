// Screen text from the one text list (TASKS P1-11): copy/texts.json → src/copy/texts.gen.ts
// (product/service/app/scripts/gen_texts.py). The copy modules now read the list; the words they
// hand to the screens stay letter for letter what they were before (P1-01 baseline).
import { describe, expect, it } from 'vitest';
import { copy } from '../src/copy';
import { backtestV2 } from '../src/copy/backtestV2';
import { blockEditor } from '../src/copy/blockEditor';
import { liveCopy } from '../src/copy/live';
import { paperV2 } from '../src/copy/paperV2';
import { settingsCopy } from '../src/copy/settings';
import { setupV2 } from '../src/copy/setupV2';
import { strategyV2 } from '../src/copy/strategyV2';
import { texts } from '../src/copy/texts.gen';

describe('text list', () => {
  it('fills named variables the way the old templates did', () => {
    expect(texts.version({ n: 3 })).toBe('버전 3');
    expect(texts.count({ n: 12 })).toBe('12개');
    expect(texts.path_count({ entry: 2, sell: 1 })).toBe('진입 경로 2 · 매도 경로 1');
    expect(texts.paper_cash({ cash: '1,000만' })).toBe('가상 시작 금액 1,000만원');
  });

  it('keeps the copy modules’ words the same', () => {
    expect(copy.common.version(7)).toBe('버전 7');
    expect(backtestV2.version(1)).toBe('버전 1');
    expect(liveCopy.version(10)).toBe('버전 10');
    expect(strategyV2.versionLabel(2)).toBe('버전 2');
    expect(blockEditor.versionChip(4, false)).toBe('버전 4');
    expect(blockEditor.versionChip(4, true)).toBe('버전 4 · 바뀐 곳 있음');
    expect(strategyV2.count(5)).toBe('5개');
    expect(strategyV2.stagesValue(6, 2, 1)).toBe('6개 · 진입 경로 2 · 매도 경로 1');
    expect(strategyV2.blanksValue(3, ['숫자', '종목'])).toBe('3개 · 숫자 · 종목');
    expect(strategyV2.pathCount(1, 2)).toBe('진입 경로 1 · 매도 경로 2');
    expect(blockEditor.narrowCounts(1, 2)).toBe('진입 경로 1 · 매도 경로 2');
    expect(strategyV2.cardLine(3, false, '11/3')).toBe('버전 3 · 백테스트 안 함 · 11/3 저장');
    expect(strategyV2.cardLine(3, true, '11/3')).toBe('버전 3 · 백테스트 함 · 11/3 저장');
    expect(paperV2.startLine('1,000만')).toBe('가상 시작 금액 1,000만원');
    expect(paperV2.startCash('500만')).toBe('가상 시작 금액 500만원');
    expect(paperV2.bench('+3.1%')).toBe('같은 기간 코스피 +3.1%');
    expect(settingsCopy.connect.stepNames).toEqual({
      token: '액세스 토큰 받기',
      account: '계좌 찾기',
      price: '삼성전자 현재가',
    });
    expect(setupV2.steps[0]).toBe('비밀번호 만들기');
  });
});
