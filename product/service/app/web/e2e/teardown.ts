// playwright.config.ts가 만든 임시 폴더(HOME · 키 파일 · 데이터)를 지워요(키 파일이 /tmp에 남지 않게).
import { rmSync } from 'node:fs';

export default function teardown(): void {
  const root = process.env.QUANT_E2E_TMP_ROOT;
  if (root) rmSync(root, { recursive: true, force: true });
}
