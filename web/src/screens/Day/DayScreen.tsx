// /day/:date renders the 기록 screen component: from 1100px the 그날 panel opens over the 기록
// page (same component instance as /history, so the page keeps its scroll and state), below that
// the full-height 그날 sheet. See History/HistoryScreen.tsx and Day/DayPanel.tsx.
export { HistoryScreen as DayScreen } from '../History/HistoryScreen';
