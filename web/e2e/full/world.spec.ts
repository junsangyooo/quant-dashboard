// The site against the real engine API (no fixtures): one dev-seed world per server, the
// production build, the production CSP. Each project is a world at 390 or 1440. The run logs in
// through the PIN page (one wrong PIN first), walks the nine screens through their links, opens
// every same-origin link they show, checks each screen (see checks.ts) and the world's key
// numbers, then logs out; a second browser without a session is sent to the PIN page.
import { expect, test, type Page } from '@playwright/test';
import { Checker, linksOn } from './checks';

type World = 'first-day' | 'paper' | 'discovery';

/** The worlds' clocks (dev-seed `now`): the browser reads the same time as the server. */
const NOW: Record<World, string> = {
  'first-day': '2026-07-01T16:10:00+09:00',
  paper: '2026-10-07T16:10:00+09:00',
  discovery: '2026-11-03T16:10:00+09:00',
};

/** Days with events each world opens on purpose (the key numbers are read there). */
const DAYS: Record<World, readonly string[]> = {
  'first-day': ['2026-07-01'],
  paper: ['2026-08-21', '2026-09-30'],
  discovery: ['2026-10-21', '2026-10-31'],
};

const PIN = '123456';
const WRONG_PIN = '000000';

async function enterPin(page: Page, digits: string, mobile: boolean): Promise<void> {
  if (mobile) {
    const pad = page.getByRole('group', { name: '숫자 키패드' });
    for (const d of digits) await pad.getByRole('button', { name: d, exact: true }).click();
  } else {
    await page.getByLabel('PIN 6자리').focus();
    await page.keyboard.type(digits);
  }
}

/** A visible link by its accessible name (390 shows the bottom tabs, 1440 the header tabs). */
function link(page: Page, name: string | RegExp) {
  return page
    .getByRole('link', { name, exact: typeof name === 'string' })
    .filter({ visible: true })
    .first();
}

test('real API: PIN, the nine screens and their links, logout', async ({ page, browser }, info) => {
  test.setTimeout(15 * 60_000);
  const world = info.project.metadata.world as World;
  const mobile = info.project.use.isMobile === true;
  await page.clock.setFixedTime(new Date(NOW[world]));
  const check = await Checker.attach(page, info);
  const visited = new Set<string>();
  const found = new Set<string>();
  const visit = async (label: string, shot?: string) => {
    await check.screen(label, shot ? { shot } : {});
    const url = new URL(page.url());
    visited.add(`${url.pathname}${url.search}${url.hash}`);
    for (const href of await linksOn(page)) found.add(href);
  };

  await test.step('no session: the PIN page, a wrong PIN, then the right one', async () => {
    // Before the PIN the shell (and the screen's first reads) answer 403 session.
    check.allow((a) => a.method === 'GET' && a.status === 403 && a.path.startsWith('/api/'));
    await page.goto('/');
    await expect(page).toHaveURL(/\/pin\?next=%2F$/);
    await expect(page.getByText('PIN 6자리').first()).toBeVisible();
    await check.screen('pin', { shot: 'pin' });

    check.allow((a) => a.method === 'POST' && a.path === '/api/auth/pin' && a.status === 403);
    await enterPin(page, WRONG_PIN, mobile);
    await expect(page.getByText(/^PIN이 맞지 않아요 · 남은 시도 [1-4]회$/)).toBeVisible();
    await check.screen('pin wrong', { shot: 'pin-wrong' });

    check.allow(() => false);
    await enterPin(page, PIN, mobile);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('banner')).toBeVisible();
  });

  await test.step('자산', async () => {
    await visit('자산', 'home');
    if (world === 'first-day') {
      await expect(page.getByText('10,005,258원').first()).toBeVisible();
      await expect(page.getByText('99.6%', { exact: true }).first()).toBeVisible();
      await expect(page.getByText(/54주/).first()).toBeVisible();
    }
  });

  await test.step('자산 · 한국 ₩ · 미국 $ (each account in its own money)', async () => {
    const home = await page.evaluate(async () => {
      const res = await fetch('/api/home', { credentials: 'same-origin' });
      return (await res.json()) as {
        pnl: { amount: number } | null;
        accounts: {
          list: { id: 'kr' | 'us'; total: number }[];
          split: { kr: number; us: number; fx: number };
        } | null;
      };
    });
    // Every world here has filled: the switch is there and the parts add up to the won.
    expect(home.accounts).not.toBeNull();
    const { kr, us, fx } = home.accounts?.split ?? { kr: 0, us: 0, fx: 0 };
    expect(kr + us + fx).toBe(home.pnl?.amount);
    const switcher = page.getByRole('radiogroup', { name: '계좌' });
    for (const [label, id] of [
      ['한국 ₩', 'kr'],
      ['미국 $', 'us'],
    ] as const) {
      await switcher.getByRole('radio', { name: label }).click();
      await expect(page).toHaveURL(new RegExp(`\\?account=${id}$`));
      const total = home.accounts?.list.find((a) => a.id === id)?.total ?? 0;
      const shown =
        id === 'kr'
          ? `${total.toLocaleString('en-US')}원`
          : `$${total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      await expect(page.locator('.t-display', { hasText: shown })).toBeVisible();
      await check.screen(`자산 ${label}`, { shot: `home-${id}` });
    }
    if (world === 'first-day') {
      // 7/1 16:10: 미국 계좌 holds only the dollars waiting for the 22:30 buy.
      await expect(page.locator('.t-display', { hasText: '$3,568.24' })).toBeVisible();
    }
    await switcher.getByRole('radio', { name: '전체' }).click();
    await expect(page).not.toHaveURL(/account=/);
  });

  await test.step('계획 (tab)', async () => {
    await link(page, '계획').click();
    await expect(page).toHaveURL(/\/plan$/);
    await visit('계획', 'plan');
    if (world === 'first-day') {
      await expect(page.getByText('99.6%', { exact: true }).first()).toBeVisible();
      await expect(page.getByText(/54주/).first()).toBeVisible();
    }
    if (world === 'discovery') {
      // The AI rule's card: the sell-condition gauge and its nearest stock.
      await expect(page.getByText('팔 조건에 가장 가까운 종목').first()).toBeVisible();
      await expect(page.getByRole('img', { name: /팔 조건까지/ }).first()).toBeVisible();
    }
  });

  await test.step('기록 (tab)', async () => {
    await link(page, '기록').click();
    await expect(page).toHaveURL(/\/history$/);
    await visit('기록', 'history');
    if (world === 'paper') {
      await expect(page.getByText('배당 20,304원').first()).toBeVisible();
    }
  });

  await test.step('그날 (days with events)', async () => {
    for (const day of DAYS[world]) {
      await page.goto(`/day/${day}`);
      await visit(`그날 ${day}`, `day-${day}`);
      if (world === 'paper' && day === '2026-08-21') {
        await expect(page.getByRole('region', { name: '리밸런싱' })).toBeVisible();
      }
      if (world === 'paper' && day === '2026-09-30') {
        // 150주 × 160원 − 15.4% 세금 (this world holds 지수 반반 alone, so more shares than §1).
        await expect(page.getByText('20,304원').first()).toBeVisible();
      }
      if (world === 'discovery' && day === '2026-10-21') {
        const card = page.getByRole('region', { name: 'AI 확인' });
        await expect(card.getByText('AI 확인 · 셀트리온')).toBeVisible();
        await expect(card.getByText('급락')).toBeVisible();
        await expect(
          card.getByText('셀트리온 · 10/20 지수 대비 −9.8% · 최근 공시 1건'),
        ).toBeVisible();
      }
      if (world === 'discovery' && day === '2026-10-31') {
        const card = page.getByRole('region', { name: '월 점검' });
        await expect(card.getByText('11월 · 보유 15종목')).toBeVisible();
      }
    }
  });

  await test.step('규칙 (tab), every rule and every lane', async () => {
    await page.goto('/');
    await link(page, '규칙').click();
    await expect(page).toHaveURL(/\/rules/);
    await visit('규칙', 'rules');
    const ids = await page.evaluate(async () => {
      const res = await fetch('/api/rules', { credentials: 'same-origin' });
      const body = (await res.json()) as { rules: { rule: { id: string } }[] };
      return body.rules.map((r) => r.rule.id);
    });
    for (const id of ids) {
      await page.goto(`/rules/${id}`);
      await visit(`규칙 ${id}`, `rules-${id}`);
      // The lane chips ('흐름'), not the canvas ('3년 발굴 흐름').
      const lanes = page.getByRole('group', { name: '흐름', exact: true });
      if ((await lanes.count()) === 0) continue;
      const names = await lanes.getByRole('button').allTextContents();
      for (const name of names) {
        await lanes.getByRole('button', { name, exact: true }).click();
        await expect(lanes.getByRole('button', { name, exact: true })).toHaveAttribute(
          'aria-pressed',
          'true',
        );
        await visit(`규칙 ${id} · ${name}`, `rules-${id}-${name.replace(/[^\w가-힣]+/g, '')}`);
      }
    }
  });

  await test.step('작동 · 모의투자·실전 · 설정 from the header', async () => {
    await page.goto('/');
    await check.settle();
    const header = page.getByRole('banner');
    // The status chip links to 작동 whatever it says.
    // The address changes before the next page renders (a transition): wait for its title, or
    // the checks read the page that is leaving (and measure its height for axe).
    await header.getByRole('link', { name: /확인|점검|실패|불가|할 일|취소/ }).click();
    await expect(page).toHaveURL(/\/health$/);
    await expect(page.getByRole('heading', { level: 1, name: '작동' })).toBeVisible();
    await visit('작동', 'health');

    await header.getByRole('link', { name: '모의투자', exact: true }).click();
    await expect(page).toHaveURL(/\/mode$/);
    await expect(page.getByRole('heading', { level: 1, name: '모의투자·실전' })).toBeVisible();
    await visit('모의투자·실전', 'mode');

    await header.getByRole('link', { name: '설정', exact: true }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole('heading', { level: 1, name: '설정' })).toBeVisible();
    await visit('설정', 'account');
    // The server has no web push yet (1·2단계): 알림 is one disabled row, nothing pretends to work.
    const notes = page.getByRole('region', { name: '알림' });
    await expect(notes.getByText('3단계에서 켤 수 있어요')).toBeVisible();
    await expect(notes.getByRole('switch')).toHaveCount(1);
    await expect(notes.getByRole('switch')).toBeDisabled();

    await page.getByRole('link', { name: '뒤로' }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('.t-display').first()).toBeVisible();
    await check.screen('자산 (뒤로)');
  });

  await test.step('every link the screens show', async () => {
    const screens = visited.size;
    const todo = [...found].filter((href) => !visited.has(href)).sort();
    for (const href of todo) {
      await page.goto(href);
      await check.screen(`link ${href}`);
      // A link never lands on the wordmark-only 404 page (it has no header).
      if (!href.startsWith('/pin')) await expect(page.getByRole('banner')).toBeVisible();
      visited.add(href);
    }
    const counts = `${String(screens)} screens + ${String(todo.length)} links = ${String(visited.size)} pages checked`;
    info.annotations.push({ type: 'pages', description: counts });
    console.log(`[${info.project.name}] ${counts}`);
  });

  await test.step('logout, then the PIN page', async () => {
    await page.goto('/account');
    await check.settle();
    await page
      .getByRole('region', { name: '기기' })
      .getByRole('button', { name: '이 기기 로그아웃', exact: true })
      .click();
    await expect(page).toHaveURL(/\/pin/);
    check.allow((a) => a.method === 'GET' && a.status === 403 && a.path.startsWith('/api/'));
    await page.goto('/plan');
    await expect(page).toHaveURL(/\/pin\?next=%2Fplan$/);
    check.expectClean('after logout');
  });

  await test.step('a second browser without a session goes to the PIN page', async () => {
    const { baseURL, viewport } = info.project.use;
    const other = await browser.newContext({
      ...(baseURL !== undefined ? { baseURL } : {}),
      ...(viewport !== undefined ? { viewport } : {}),
    });
    const page2 = await other.newPage();
    await page2.goto('/history');
    await expect(page2).toHaveURL(/\/pin\?next=%2Fhistory$/);
    await expect(page2.getByText('PIN 6자리').first()).toBeVisible();
    await other.close();
  });
});
