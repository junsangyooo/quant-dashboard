// Unknown path: the wordmark only, as in the existing app's 404 rule (no links out).
import { copy } from '../copy';
import styles from './NotFoundScreen.module.css';

export function NotFoundScreen() {
  return (
    <main id="main" className={styles.page}>
      <h1 className="t-title">{copy.wordmark}</h1>
    </main>
  );
}
