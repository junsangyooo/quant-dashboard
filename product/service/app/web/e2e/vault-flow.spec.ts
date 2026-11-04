// 금고 흐름(P1-02 ⑤ · QUALITY S5 · SPEC 7-4): 돈이 움직이는 요청은 서버가 403 `need_confirm`으로 거절하고, 화면이 비밀번호
// 창(V2-33 · ConfirmHost)을 띄워 `/api/confirm`으로 1회용 토큰을 받은 뒤 같은 요청을 `x-confirm-token`으로 한 번 더 보내요.
// 돈이 움직이는 일 가운데 실전 운용 없이도 닿는 '앱 데이터 삭제'(`DELETE /api/data` · 설정 › 데이터)로 확인해요.
import { expect, test, type Page } from '@playwright/test';

const PASSWORD = 'correct horse 9';
const CONFIRM_HEADER = 'x-confirm-token';

interface Seen {
  method: string;
  path: string;
  status: number;
  confirmToken: string | undefined;
}

/** 화면이 보낸 `DELETE /api/data` · `POST /api/confirm` 요청과 응답을 순서대로 적어 둬요(화면 조회 GET은 뺌). */
function record(page: Page): Seen[] {
  const seen: Seen[] = [];
  page.on('response', (res) => {
    const req = res.request();
    const path = new URL(req.url()).pathname;
    if ((path !== '/api/data' && path !== '/api/confirm') || req.method() === 'GET') return;
    seen.push({
      method: req.method(),
      path,
      status: res.status(),
      confirmToken: req.headers()[CONFIRM_HEADER],
    });
  });
  return seen;
}

test('돈이 움직이는 요청: 토큰 없이 403 → 비밀번호 창 → 토큰으로 다시 보내 성공', async ({
  page,
  context,
}) => {
  const r = context.request; // 브라우저 문맥과 쿠키를 같이 써요
  const setup = await r.post('/api/setup', {
    data: { password: PASSWORD, password2: PASSWORD, adult: true, terms: true },
  });
  expect(setup.ok(), await setup.text()).toBeTruthy();
  const login = await r.post('/api/login', { data: { password: PASSWORD } });
  expect(login.ok(), await login.text()).toBeTruthy();
  const csrf = (await context.cookies()).find((c) => c.name === 'qm_csrf')?.value;
  expect(csrf).toBeTruthy();
  const csrfHeaders = { 'x-csrf-token': csrf ?? '' };

  // ① 토큰 없이 보내면 403이고 비밀번호 창을 띄우라는 표시가 와요. 데이터는 그대로예요(로그인 유지).
  const bare = await r.delete('/api/data', { headers: csrfHeaders });
  expect(bare.status()).toBe(403);
  expect(await bare.json()).toMatchObject({
    need_confirm: true,
    action: 'data_delete',
    title: '앱 데이터 삭제',
  });
  const state = await r.get('/api/state');
  expect(state.ok()).toBeTruthy();

  // ② 지어낸 토큰으로 보내도 403이에요(토큰은 서버가 내준 것만 · 1회용).
  const fake = await r.delete('/api/data', {
    headers: { ...csrfHeaders, [CONFIRM_HEADER]: 'not-a-token' },
  });
  expect(fake.status()).toBe(403);

  // ③ 화면: 설정 › 데이터 › '앱 데이터 삭제' → 403 → 비밀번호 창 → 틀린 비밀번호는 창에 서버 글 → 맞는 비밀번호 →
  //    토큰으로 다시 보내 성공 → 처음 설정 화면으로.
  const seen = record(page);
  await page.goto('/settings/data');
  await page.getByRole('button', { name: '앱 데이터 삭제' }).click();

  const sheet = page.getByRole('dialog');
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('heading', { name: '앱 데이터 삭제' })).toBeVisible();
  await expect(sheet.getByText('이 일은 비밀번호를 한 번 더 받아요')).toBeVisible();

  await sheet.getByLabel('비밀번호').fill('wrong password 1');
  await sheet.getByRole('button', { name: '확인' }).click();
  await expect(sheet.getByText(/비밀번호가 맞지 않아요/)).toBeVisible();
  await expect(sheet).toBeVisible();

  await sheet.getByLabel('비밀번호').fill(PASSWORD);
  await sheet.getByRole('button', { name: '확인' }).click();
  await expect(page).toHaveURL(/\/setup$/);
  await expect(sheet).toBeHidden();

  // 오간 순서: DELETE 403(토큰 없음) → confirm 실패 → confirm 200 → DELETE 200(토큰 있음)
  const flow = seen.map(
    (s) => `${s.method} ${s.path} ${s.status} ${s.confirmToken ? 'token' : '-'}`,
  );
  expect(flow).toEqual([
    'DELETE /api/data 403 -',
    'POST /api/confirm 401 -',
    'POST /api/confirm 200 -',
    'DELETE /api/data 200 token',
  ]);
  const token = seen[3]?.confirmToken ?? '';
  expect(token.length).toBeGreaterThan(16);

  // ④ 지운 뒤에는 계정이 없어요(처음 설정부터) · 같은 토큰을 다시 쓸 수도 없어요.
  const after = await r.get('/api/state');
  expect(after.ok()).toBeTruthy();
  expect(await after.json()).toMatchObject({ setup: false });
  const reuse = await r.delete('/api/data', {
    headers: { ...csrfHeaders, [CONFIRM_HEADER]: token },
  });
  expect([401, 403]).toContain(reuse.status());
});
