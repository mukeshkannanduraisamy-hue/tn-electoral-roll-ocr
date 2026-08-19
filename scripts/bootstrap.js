#!/usr/bin/env node
/**
 * Cross-platform bootstrap runner for OCR Workspace.
 * Dispatches to bootstrap.ps1 on Windows or bootstrap.sh on Unix.
 */

const { spawn } = require('child_process');
const path = require('path');

const isWindows = process.platform === 'win32';
const repoRoot = path.resolve(__dirname, '..');
const args = process.argv.slice(2);

console.log('\x1b[36m=== OCR Workspace Bootstrap ===\x1b[0m\n');

let child;
if (isWindows) {
  const psScript = path.join(repoRoot, 'scripts', 'bootstrap.ps1');
  child = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', psScript, ...args], {
    cwd: repoRoot,
    stdio: 'inherit',
  });
} else {
  const shScript = path.join(repoRoot, 'scripts', 'bootstrap.sh');
  child = spawn('bash', [shScript, ...args], {
    cwd: repoRoot,
    stdio: 'inherit',
  });
}

child.on('close', (code) => {
  if (code === 0) {
    console.log('\n\x1b[32mBootstrap finished successfully!\x1b[0m');
    console.log('Run \x1b[36mnpm run dev\x1b[0m to start both servers.\n');
  } else {
    console.error(`\n\x1b[31mBootstrap exited with error code ${code}\x1b[0m\n`);
  }
  process.exit(code || 0);
});
