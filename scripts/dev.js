#!/usr/bin/env node
/**
 * Cross-platform dev server runner for OCR Workspace.
 * Runs on Windows, macOS, Linux, and WSL.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const isWindows = process.platform === 'win32';
const repoRoot = path.resolve(__dirname, '..');
const apiDir = path.join(repoRoot, 'apps', 'api');
const webDir = path.join(repoRoot, 'apps', 'web');

const venvPython = isWindows
  ? path.join(apiDir, '.venv', 'Scripts', 'python.exe')
  : path.join(apiDir, '.venv', 'bin', 'python');

if (!fs.existsSync(venvPython)) {
  console.error('\x1b[31m[ERROR] Backend virtual environment not found at:\x1b[0m', venvPython);
  console.error('\x1b[33mPlease run the setup first:\x1b[0m');
  if (isWindows) {
    console.error('  .\\setup.bat  or  npm run bootstrap');
  } else {
    console.error('  ./setup.sh   or  npm run bootstrap');
  }
  process.exit(1);
}

const args = process.argv.slice(2);
const isReload = args.includes('--reload');

console.log('\x1b[36m=== Starting OCR Workspace Dev Servers ===\x1b[0m');

// 1. Backend process
const uvicornArgs = ['-m', 'uvicorn', 'app.main:app', '--port', '8000', '--host', '0.0.0.0'];
if (isReload) {
  uvicornArgs.push('--reload');
  console.log('\x1b[33mAuto-reload ON - editing a .py file will restart the backend.\x1b[0m');
}

console.log('\x1b[32m[backend]\x1b[0m Starting FastAPI on \x1b[4mhttp://localhost:8000\x1b[0m ...');
const backend = spawn(venvPython, uvicornArgs, {
  cwd: apiDir,
  stdio: 'inherit',
  env: { ...process.env },
});

// 2. Frontend process
let frontend = null;
if (fs.existsSync(path.join(webDir, 'package.json'))) {
  console.log('\x1b[35m[frontend]\x1b[0m Starting Next.js on \x1b[4mhttp://localhost:3000\x1b[0m ...');
  const npmCmd = isWindows ? 'npm.cmd' : 'npm';
  frontend = spawn(npmCmd, ['run', 'dev'], {
    cwd: webDir,
    stdio: 'inherit',
    env: { ...process.env },
  });
} else {
  console.log('\x1b[33mapps/web/package.json not found. Running backend only.\x1b[0m');
}

console.log('\n\x1b[36mPress Ctrl+C to stop all servers.\x1b[0m\n');

function cleanup() {
  console.log('\n\x1b[33mShutting down servers...\x1b[0m');
  if (backend && !backend.killed) {
    if (isWindows) {
      spawn('taskkill', ['/pid', backend.pid.toString(), '/f', '/t']);
    } else {
      backend.kill('SIGTERM');
    }
  }
  if (frontend && !frontend.killed) {
    if (isWindows) {
      spawn('taskkill', ['/pid', frontend.pid.toString(), '/f', '/t']);
    } else {
      frontend.kill('SIGTERM');
    }
  }
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
