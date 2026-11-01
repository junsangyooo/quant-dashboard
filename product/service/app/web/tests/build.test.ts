// @vitest-environment node
// The production build refuses any module under src/fixtures/ (vite.config.ts).
import { describe, expect, it, vi } from 'vitest';
import { noFixturesInProduction } from '../vite.config';

type ConfigResolved = (config: { mode: string }) => void;
type GenerateBundle = (
  this: { error: (message: string) => void },
  options: unknown,
  bundle: unknown,
) => void;

function build(mode: string, moduleIds: string[]) {
  const plugin = noFixturesInProduction();
  const error = vi.fn();
  (plugin.configResolved as ConfigResolved)({ mode });
  (plugin.generateBundle as GenerateBundle).call(
    { error },
    {},
    { 'assets/index.js': { type: 'chunk', moduleIds } },
  );
  return error;
}

describe('fixtures never ship', () => {
  it('fails a production build that contains a fixture module', () => {
    const error = build('production', ['/w/web/src/main.tsx', '/w/web/src/fixtures/runtime.ts']);
    expect(error).toHaveBeenCalledOnce();
    expect(error.mock.calls[0]?.[0]).toContain('/src/fixtures/runtime.ts');
  });

  it('passes a clean production build and the e2e build', () => {
    expect(build('production', ['/w/web/src/main.tsx'])).not.toHaveBeenCalled();
    expect(build('e2e', ['/w/web/src/fixtures/runtime.ts'])).not.toHaveBeenCalled();
  });
});
