import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..');

/** 起服务前重建测试库（独立 SQLite 临时库，见 prepare_db.py）。 */
export default function globalSetup(): void {
  execFileSync('uv', ['run', 'python', '../e2e/prepare_db.py'], {
    cwd: path.join(repo, 'backend'),
    stdio: 'inherit',
    env: { ...process.env, DATABASE_URL: 'sqlite:///../e2e/.tmp/e2e.db' },
  });
}
