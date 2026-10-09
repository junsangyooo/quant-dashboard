// Every file in src/fixtures/bundles/ is a bundle named after its state id; adding a file is
// enough to make `?fixture=<id>` work. Bundles load lazily, one per page.
import type { FixtureBundle } from './types';

const modules = import.meta.glob<{ default: FixtureBundle }>('./bundles/*.ts');

export function bundleIds(): string[] {
  return Object.keys(modules)
    .map((path) => path.replace('./bundles/', '').replace(/\.ts$/, ''))
    .sort();
}

export async function loadBundle(id: string): Promise<FixtureBundle | null> {
  const load = modules[`./bundles/${id}.ts`];
  if (!load) return null;
  const bundle = (await load()).default;
  if (bundle.id !== id) throw new Error(`fixture file ${id}.ts declares id "${bundle.id}"`);
  return bundle;
}
