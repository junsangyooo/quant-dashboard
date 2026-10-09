// 입장 placeholder: wordmark + 'PIN 6자리' only — no account figure is ever shown here.
import { copy } from '../copy';
import { pageTitle, useDocumentTitle } from '../shell/page';
import styles from './PinScreen.module.css';

export function PinScreen() {
  useDocumentTitle(pageTitle('pin'));
  return (
    <main id="main" className={styles.pin}>
      <h1 className="t-title">{copy.wordmark}</h1>
      <p className="t-body">{copy.pin.prompt}</p>
    </main>
  );
}
