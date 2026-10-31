/**
 * The bundle-budget check (T4.11, 07 §11).
 *
 * Runs against `dist/` after `vite build` and fails when the shipped JavaScript or CSS
 * grows past the budget. Sizes are gzipped because that is what the browser downloads;
 * raw bytes would make a hashed filename's worth of difference look like a regression.
 *
 * The budget is deliberately a ceiling, not a target: current sizes sit ~20% below it, so
 * an ordinary screen fits and a dependency that pulls in its own date library does not.
 * Fonts are excluded — they are static assets served from the build (T9.7 checks them),
 * not per-page weight.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const ASSETS = fileURLToPath(new URL('../dist/assets/', import.meta.url));
const KB = 1024;

const BUDGET = {
    javascript: 300 * KB,
    css: 20 * KB,
    // Catches one dependency being imported into every chunk rather than split out.
    chunk: 200 * KB,
};

function gzipped(bytes) {
    return gzipSync(bytes, { level: 9 }).length;
}

let files;
try {
    files = readdirSync(ASSETS);
} catch {
    console.error(`No build output at ${ASSETS}. Run \`pnpm build\` first.`);
    process.exit(1);
}

const totals = { javascript: 0, css: 0 };
const rows = [];

for (const file of files) {
    const path = join(ASSETS, file);
    if (!statSync(path).isFile()) {
        continue;
    }
    if (file.endsWith('.js')) {
        const size = gzipped(readFileSync(path));
        totals.javascript += size;
        rows.push({ kind: 'javascript', file, size });
    } else if (file.endsWith('.css')) {
        const size = gzipped(readFileSync(path));
        totals.css += size;
        rows.push({ kind: 'css', file, size });
    }
}

const failures = [];

for (const [kind, budget] of Object.entries(BUDGET)) {
    const size = kind === 'chunk' ? Math.max(0, ...rows.map((row) => row.size)) : totals[kind];
    const label = kind === 'chunk' ? 'largest chunk' : kind;
    const verdict = size > budget ? 'over' : 'ok';
    console.log(
        `${verdict.padEnd(5)} ${label.padEnd(14)} ${(size / KB).toFixed(1).padStart(7)} kB gzip` +
            ` / ${(budget / KB).toFixed(0).padStart(4)} kB`,
    );
    if (size > budget) {
        failures.push(
            `${label} is ${(size / KB).toFixed(1)} kB, budget ${(budget / KB).toFixed(0)} kB`,
        );
    }
}

if (failures.length > 0) {
    console.error(`\nBundle budget exceeded:\n${failures.map((line) => `  - ${line}`).join('\n')}`);
    console.error('Split the new code behind a dynamic import, or raise the budget with a reason.');
    process.exit(1);
}

console.log(`\n${rows.length} asset(s) within budget.`);
