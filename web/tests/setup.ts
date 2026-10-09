import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});

// jsdom does not implement scrolling or the modal half of <dialog>.
window.scrollTo = () => undefined;

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
