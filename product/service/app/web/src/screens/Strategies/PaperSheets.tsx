// MVP-16 모의투자 시작 확인 (기본 · 다른 모의투자 실행 중) and MVP-11 모의투자 끝내기 확인.
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { isApiError } from '../../api/client';
import { useHome, usePost, usePreview } from '../../api/mvp';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { KeyValue } from '../../components/Card';
import { TextField } from '../../components/Field';
import { Sheet } from '../../components/Sheet';
import { copy } from '../../copy';
import { strategyCopy } from '../../copy/strategy';
import { formatMonthDayWeekday, formatNumber, kstDateKey } from '../../lib/format';
import { daysBetween } from '../../charts/geometry/scale';
import { startDay } from '../../lib/runDates';

const t = strategyCopy.start;

export function parseWon(text: string): number | null {
  const digits = text.replace(/[^0-9]/g, '');
  return digits ? Number(digits) : null;
}

export function wonInput(text: string): string {
  const n = parseWon(text);
  return n === null ? '' : formatNumber(n);
}

export function StartSheet({
  strategy,
  versionId,
  versionNo,
  onClose,
}: {
  strategy: string;
  versionId: number;
  versionNo: number;
  onClose: () => void;
}) {
  const home = useHome().data;
  const navigate = useNavigate();
  const [cash, setCash] = useState(() => formatNumber(10_000_000));
  const start = usePost<{ version_id: number; cash: number }, unknown>('/api/paper/start');
  const amount = parseWon(cash);
  const ok = amount !== null && amount >= 100_000 && amount <= 10_000_000_000;
  // 첫 확인 · 첫 모의 체결: 서버가 시작할 때 쓰는 규칙과 같은 계산(GET /api/paper/preview)
  const preview = usePreview(versionId);
  const first = preview.data;
  const other = home?.running ? home : null;
  return (
    <Sheet title={t.title} onClose={onClose}>
      <KeyValue label={t.strategy}>{t.strategyLine(strategy, versionNo)}</KeyValue>
      <TextField
        label={t.cash}
        inputMode="numeric"
        value={cash}
        placeholder={formatNumber(10_000_000)}
        unit={t.unit}
        hint={t.cashHint}
        onChange={(e) => {
          setCash(wonInput(e.target.value));
        }}
      />
      {first ? (
        <Box
          tone="info"
          icon="clock"
          title={t.first(
            formatMonthDayWeekday(first.check_d),
            first.check_time,
            formatMonthDayWeekday(first.fill_d),
          )}
        >
          {first.check_now
            ? t.firstBodyNow(formatMonthDayWeekday(first.fill_d))
            : t.firstBodyLater(
                formatMonthDayWeekday(first.check_d),
                formatMonthDayWeekday(first.fill_d),
              )}
        </Box>
      ) : preview.isError ? (
        <Box tone="error" title={t.previewFailed} strongTitle role="alert">
          <span>
            {isApiError(preview.error) ? preview.error.message : copy.common.noConnection}
          </span>
          <span>
            <Button kind="default" onClick={() => void preview.refetch()}>
              {t.previewRetry}
            </Button>
          </span>
        </Box>
      ) : (
        <Box tone="info" icon="wait" title={t.previewLoading} role="status" />
      )}
      {other ? (
        <Box tone="warn" title={t.otherTitle}>
          {t.otherBody(other.strategy, other.version_no, startDay(other))}
        </Box>
      ) : null}
      {start.error ? (
        <p className="t-caption c-error">
          {isApiError(start.error) ? start.error.message : copy.common.noConnection}
        </p>
      ) : null}
      <div className="buttons">
        <Button kind="default" onClick={onClose}>
          {copy.common.dismiss}
        </Button>
        <Button
          kind="primary"
          disabled={!ok || start.isPending || !first}
          onClick={() => {
            if (amount === null) return;
            start.mutate(
              { version_id: versionId, cash: amount },
              {
                onSuccess: () => {
                  onClose();
                  void navigate('/');
                },
              },
            );
          }}
        >
          {other ? t.goReplace : t.go}
        </Button>
      </div>
    </Sheet>
  );
}

export function EndSheet({
  strategy,
  versionNo,
  since,
  lastEval,
  held,
  onClose,
}: {
  strategy: string;
  versionNo: number;
  since: string;
  /** 마지막 평가에 쓰는 일봉 날짜(그날까지 확인한 종가). */
  lastEval: string | null;
  held: number;
  onClose: () => void;
}) {
  const e = strategyCopy.end;
  const navigate = useNavigate();
  const stop = usePost<undefined, unknown>('/api/paper/stop');
  const today = kstDateKey(new Date());
  const days = daysBetween(kstDateKey(since), today) + 1;
  return (
    <Sheet title={e.title} onClose={onClose}>
      <KeyValue label={e.line(strategy, versionNo)}>
        {e.since(startDay({ started_at: since }), days)}
      </KeyValue>
      <p className="t-body">{e.body(lastEval ? formatMonthDayWeekday(lastEval) : '', held)}</p>
      {stop.error ? (
        <p className="t-caption c-error">
          {isApiError(stop.error) ? stop.error.message : copy.common.noConnection}
        </p>
      ) : null}
      <div className="buttons">
        <Button kind="default" onClick={onClose}>
          {copy.common.dismiss}
        </Button>
        <Button
          kind="danger"
          disabled={stop.isPending}
          onClick={() => {
            stop.mutate(undefined, {
              onSuccess: () => {
                onClose();
                void navigate('/');
              },
            });
          }}
        >
          {e.go}
        </Button>
      </div>
    </Sheet>
  );
}
