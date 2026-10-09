// 그날 panel placeholder: 390 full-height sheet (× closes back to 기록), date as the title.
import { useParams } from 'react-router';
import { kstDateKey, formatMonthDayWeekday } from '../lib/format';
import { PageTitle } from '../shell/PageTitle';
import { pageTitle, useDocumentTitle } from '../shell/page';
import { copy } from '../copy';

function parseDate(raw: string | undefined): string | null {
  if (!raw) return null;
  try {
    return kstDateKey(raw);
  } catch {
    return null;
  }
}

export function DayScreen() {
  const { date } = useParams();
  const day = parseDate(date);
  useDocumentTitle(pageTitle('day'));
  return (
    <PageTitle backTo="/history" close>
      {day ? formatMonthDayWeekday(day) : copy.pages.day}
    </PageTitle>
  );
}
