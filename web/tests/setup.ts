import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { resetClient } from '../src/api/client';
import { resetDataLayer } from '../src/api/queries';

afterEach(() => {
  cleanup();
  resetClient();
  resetDataLayer();
});

// jsdom does not implement scrolling or the modal half of <dialog>. (Node-environment tests,
// like build.test.ts, have no window.)
if (typeof window !== 'undefined') window.scrollTo = () => undefined;

if (typeof HTMLDialogElement !== 'undefined') {
  const proto = HTMLDialogElement.prototype;
  if (typeof proto.showModal !== 'function' || !('__polyfilled' in proto)) {
    Object.defineProperty(proto, '__polyfilled', { value: true });
    proto.showModal = function showModal(this: HTMLDialogElement) {
      this.setAttribute('open', '');
      const auto = this.querySelector<HTMLElement>('[autofocus]');
      auto?.focus();
    };
    proto.close = function close(this: HTMLDialogElement) {
      this.removeAttribute('open');
      this.dispatchEvent(new Event('close'));
    };
  }
}
