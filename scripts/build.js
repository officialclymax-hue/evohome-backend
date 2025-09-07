// Minimal "build": copy src to dist and copy seed json.
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const from = path.join(__dirname, '..', 'src');
const to = path.join(__dirname, '..', 'dist');
fs.rmSync(to, { recursive: true, force: true });
fs.mkdirSync(to, { recursive: true });

// copy all .js and inline admin page
(function copyDir(src, dst){
  fs.mkdirSync(dst, { recursive: true });
  for (const f of fs.readdirSync(src)) {
    const s = path.join(src, f);
    const d = path.join(dst, f);
    const stat = fs.statSync(s);
    if (stat.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
})(from, to);

// copy seed json
const seedFrom = path.join(__dirname, '..', 'src', 'seed');
const seedTo = path.join(to, 'seed');
fs.mkdirSync(seedTo, { recursive: true });
for (const f of fs.readdirSync(seedFrom)) {
  if (f.endsWith('.json')) fs.copyFileSync(path.join(seedFrom, f), path.join(seedTo, f));
}

console.log('Build complete.');
