// Words of the '지금' box rows (CONTRACT NowBlock). The server sends only data — kv key codes
// with dates, counts, names and codes ('-' for none), an order's instrument name or 환전
// direction code, an earnings period ('2026Q3') — and the card words them here.
import { sideName } from '../../api/adapters';
import type { AiJudgment, Side } from '../../api/types';
import { dayCopy } from '../../copy/day';
import { rulesCopy as rc } from '../../copy/rules';
import { formatMonthDay, formatNumber } from '../../lib/format';
import { tokensLabel, votesLabel } from '../Day/dayModel';

/** A kv row on the card: muted label (or none), the value, and the right-hand note. */
export interface KvView {
  label: string | null;
  value: string;
  note: string | null;
}

const NONE = '-';

function day(value: string): string {
  return value === NONE ? rc.now.none : formatMonthDay(value);
}

function count(value: string): number | null {
  if (value === NONE) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function counted(value: string, word: (n: number) => string = (n) => formatNumber(n)): string {
  const n = count(value);
  return n === null ? rc.now.none : word(n);
}

function isKey<T extends object>(map: T, key: string | undefined): key is Extract<keyof T, string> {
  return key !== undefined && Object.hasOwn(map, key);
}

function state(note: string | undefined): string | null {
  return isKey(rc.now.kv.state, note) ? rc.now.kv.state[note] : (note ?? null);
}

const VOTES = new Set(['hold', 'weaken', 'invalidated', 'switch', 'keep']);

/** 'hold,invalidated' → "'유지' · '반증'" (the last twice-asked judgment). */
function votes(value: string): string {
  const parts = value.split(',').filter((v) => VOTES.has(v));
  return votesLabel(parts as NonNullable<AiJudgment['votes']>) ?? rc.now.none;
}

/** A kv row in words. Keys the screen does not know keep the server's text as it is. */
export function kvView(key: string, value: string, note?: string): KvView {
  const k = rc.now.kv;
  const ai = dayCopy.ai;
  switch (key) {
    case 'krClose':
      return { label: k.krClose, value: day(value), note: state(note) };
    case 'usClose':
      return { label: k.usClose, value: day(value), note: state(note) };
    case 'filings':
      return {
        label: k.filings,
        value: value === NONE ? rc.now.none : value,
        note: note === undefined ? null : counted(note, k.newCount),
      };
    case 'metricTable':
      return {
        label: k.metricTable,
        value: day(value),
        note: note === undefined ? null : counted(note, k.stocks),
      };
    case 'verdict':
      return {
        label: k.verdict,
        value: isKey(ai.verdict, value) ? ai.verdict[value] : value,
        note: isKey(ai.trigger, note) ? ai.trigger[note] : (note ?? null),
      };
    case 'votes':
      return { label: k.votes, value: votes(value), note: null };
    case 'tokens': {
      const n = count(value);
      return { label: null, value: n === null ? rc.now.none : tokensLabel(n), note: null };
    }
    case 'hits':
    case 'judgments':
    case 'sells':
    case 'buys':
    case 'metrics':
    case 'hold':
    case 'weaken':
    case 'invalidated':
      return { label: k[key], value: counted(value), note: null };
    case 'picks':
    case 'companies':
    case 'candidates':
      return { label: k[key], value: counted(value, k.stocks), note: null };
    case 'newFilings':
      return { label: k.newFilings, value: counted(value, k.cases), note: null };
    case 'lastDiscovery':
      return { label: k.lastDiscovery, value: day(value), note: null };
    case 'targetEach':
      return { label: k.targetEach, value: counted(value, (n) => `${n.toFixed(1)}%`), note: null };
    default:
      return { label: key === '' ? null : key, value, note: note ?? null };
  }
}

/** '매도 · 삼성전자', '환전 · 원 → 달러' (text = the instrument's name or the direction code). */
export function orderText(side: Side, text: string): string {
  const what = isKey(rc.now.fxDirection, text) ? rc.now.fxDirection[text] : text;
  return rc.now.order(sideName(side), what);
}

/** '2026Q3' → '3Q'; another period stays as the server wrote it. */
export function periodText(period: string): string {
  const m = /^\d{4}Q([1-4])$/.exec(period);
  return m?.[1] ? rc.now.quarter(m[1]) : period;
}
