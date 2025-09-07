import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const copyDir = (src, dst) => {
  fs.mkdirSync(dst, { recursive: true });
  for (const f of fs.readdirSync(src)) {
    const s = path.join(src, f);
    const d = path.join(dst, f);
    const st = fs.statSync(s);
    if (st.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
};

const SRC = path.join(__dirname, '..', 'src');
const DIST = path.join(__dirname, '..', 'dist');

fs.rmSync(DIST, { recursive: true, force: true });
copyDir(SRC, DIST);

const seedFrom = path.join(SRC, 'seed');
const seedTo = path.join(DIST, 'seed');
fs.mkdirSync(seedTo, { recursive: true });
for (const f of fs.readdirSync(seedFrom)) {
  if (f.endsWith('.json')) fs.copyFileSync(path.join(seedFrom, f), path.join(seedTo, f));
}
console.log('Build complete');
