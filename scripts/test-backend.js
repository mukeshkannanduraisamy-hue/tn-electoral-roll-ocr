#!/usr/bin/env node
/**
 * Cross-platform backend test runner.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const isWindows = process.platform === 'win32';
const repoRoot = path.resolve(__dirname, '..');
const apiDir = path.join(repoRoot, 'apps', 'api');

const venvPython = isWindows
  ? path.join(apiDir, '.venv', 'Scripts', 'python.exe')
  : path.join(apiDir, '.venv', 'bin', 'python');

if (!fs.existsSync(venvPython)) {
  console.error('\x1b[31m[ERROR] Backend virtual environment not found at:\x1b[0m', venvPython);
  console.error('Please run setup first.');
  process.exit(1);
}

const rawArgs = process.argv.slice(2);
const normalizedArgs = rawArgs.map(arg => {
  if (arg.startsWith('apps/api/') || arg.startsWith('apps\\api\\')) {
    return arg.slice(9);
  }
  return arg;
});

const pytestArgs = ['-m', 'pytest', ...(normalizedArgs.length > 0 ? normalizedArgs : ['tests'])];

console.log('\x1b[36mRunning backend tests with pytest...\x1b[0m\n');

const child = spawn(venvPython, pytestArgs, {
  cwd: apiDir,
  stdio: 'inherit',
  env: { ...process.env },
});

child.on('close', (code) => {
  process.exit(code || 0);
});
