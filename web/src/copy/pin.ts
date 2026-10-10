// SCR-PIN 입장. Sources: 기획.md §5 SCR-PIN (lines 340–376), Figma 1:51276 · 1:51328 · 1:51378,
// autotrade/CONTRACT.md (no-pin, the server CLI). Shared words (PIN 6자리, 잊었을 때 …) stay in
// copy.ts → copy.pin. Strings marked NEW are not in the spec or Figma; they follow its pattern.

export const pinCopy = {
  /** 'PIN이 맞지 않아요 · 남은 시도 2회' (1:39527). */
  wrong: (remaining: number) => `PIN이 맞지 않아요 · 남은 시도 ${String(remaining)}회`,
  /** '16:40까지 잠김 · 이 접속 위치' (1:48835). */
  lockedHere: (time: string) => `${time}까지 잠김 · 이 접속 위치`,
  /** Global cap (spec: '시도가 많아요 · [n]분 뒤 다시'). */
  lockedEverywhere: (minutes: number) => `시도가 많아요 · ${String(minutes)}분 뒤 다시`,
  lockedNote: '이미 열린 기기는 그대로 써요 · 실전 끄기도 그 기기에서 돼요',
  /** NEW — 403 locked scope 'hold': a day of wrong PINs closed new logins until the server opens
   * them (CONTRACT.md 쓰기). No time: it does not end by itself. */
  lockedHold: '새 로그인이 닫혔어요 · 서버에서 열어야 해요',
  /** NEW — guidance under the hold, same shape as noPinHelp. */
  lockedHoldHelp: '틀린 PIN이 많았어요 · 서버에서 아래 명령으로 열어요 · Claude에게 요청',
  /** The command from CONTRACT.md that reopens login. */
  unlockCommand: 'python -m autotrade.jobs unlock',
  /** NEW — 403 no-pin: the first PIN is set only on the server (CONTRACT.md). */
  noPin: 'PIN이 아직 없어요 · 서버에서 먼저 정해요',
  /** NEW — guidance under no-pin, same shape as copy.pin.forgotHelp. */
  noPinHelp: '서버에서 아래 명령으로 정해요 · Claude에게 요청',
  /** The command from CONTRACT.md (PIN on standard input, twice). */
  noPinCommand: 'python -m autotrade.jobs set-pin',
  /** NEW — screen-reader text of the small spinner while the PIN is checked. */
  checking: '확인 중',
  /** NEW — anything else (server error, no connection): the cells clear for another try. */
  failed: '입장하지 못했어요 · 다시 입력',
  /** NEW — accessible name of the keypad group. */
  keypad: '숫자 키패드',
} as const;
