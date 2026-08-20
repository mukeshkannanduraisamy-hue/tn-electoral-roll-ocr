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

function loadEnv() {
  const envPath = path.join(repoRoot, '.env');
  if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, 'utf8');
    content.split(/\r?\n/).forEach((line) => {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
        const idx = trimmed.indexOf('=');
        const key = trimmed.slice(0, idx).trim();
        const val = trimmed.slice(idx + 1).trim().replace(/^["']|["']$/g, '');
        if (!process.env[key]) {
          process.env[key] = val;
        }
      }
    });
  }
}

loadEnv();

const serenaDir = path.join(repoRoot, 'apps', 'serena-ocr');

const args = process.argv.slice(2);
const isReload = args.includes('--reload');

const backendHost = process.env.BACKEND_HOST || '127.0.0.1';
const backendPort = process.env.BACKEND_PORT || '8080';
const webHost = process.env.HOST || '127.0.0.1';
const webPort = process.env.PORT || '3000';
const serenaPort = process.env.SERENA_PORT || '3002';
const backendUrl = process.env.BACKEND_URL || `http://${backendHost}:${backendPort}`;

console.log('\x1b[36m===================================================\x1b[0m');
console.log('\x1b[36m    OCR Workspace - Starting Local Servers\x1b[0m');
console.log('\x1b[36m===================================================\x1b[0m\n');

// 1. Backend process
const uvicornArgs = ['-m', 'uvicorn', 'app.main:app', '--host', backendHost, '--port', backendPort];
if (isReload) {
  uvicornArgs.push('--reload');
  console.log('\x1b[33mAuto-reload ON - editing a .py file will restart the backend.\x1b[0m');
}

console.log(`\x1b[32m[backend]\x1b[0m FastAPI running on      \x1b[4mhttp://${backendHost}:${backendPort}\x1b[0m (API Docs: \x1b[4mhttp://${backendHost}:${backendPort}/docs\x1b[0m)`);
const backend = spawn(venvPython, uvicornArgs, {
  cwd: apiDir,
  stdio: 'inherit',
  env: { ...process.env },
});

const npmCmd = isWindows ? 'npm.cmd' : 'npm';

// 2. Primary Frontend process
let frontend = null;
if (fs.existsSync(path.join(webDir, 'package.json'))) {
  console.log(`\x1b[35m[web-ui]\x1b[0m  Next.js running on     \x1b[1m\x1b[4mhttp://${webHost}:${webPort}\x1b[0m`);
  frontend = spawn(npmCmd, ['run', 'dev', '--', '-H', webHost, '-p', webPort], {
    cwd: webDir,
    stdio: 'inherit',
    shell: isWindows,
    env: {
      ...process.env,
      HOST: webHost,
      PORT: webPort,
      BACKEND_URL: backendUrl,
      BACKEND_HOST: backendHost,
      BACKEND_PORT: backendPort,
    },
  });
}

// 3. Standalone Serena Batch OCR Frontend process
let serenaFrontend = null;
if (fs.existsSync(path.join(serenaDir, 'package.json'))) {
  console.log(`\x1b[36m[serena]\x1b[0m  Serena OCR running on \x1b[1m\x1b[4mhttp://${webHost}:${serenaPort}\x1b[0m\n`);
  serenaFrontend = spawn(npmCmd, ['run', 'dev', '--', '-H', webHost, '-p', serenaPort], {
    cwd: serenaDir,
    stdio: 'inherit',
    shell: isWindows,
    env: {
      ...process.env,
      HOST: webHost,
      PORT: serenaPort,
      BACKEND_URL: backendUrl,
      BACKEND_HOST: backendHost,
      BACKEND_PORT: backendPort,
    },
  });
}

const displayHost = webHost === '0.0.0.0' ? 'localhost' : webHost;
console.log(`\x1b[36m✨ Serena Batch OCR Ready:\x1b[0m \x1b[1m\x1b[4mhttp://${displayHost}:${serenaPort}\x1b[0m`);
console.log(`\x1b[35m📄 Main Electoral UI Ready:\x1b[0m \x1b[1m\x1b[4mhttp://${displayHost}:${webPort}\x1b[0m`);
console.log('Press \x1b[33mCtrl+C\x1b[0m in this terminal to stop all servers.\n');

function cleanup() {
  console.log('\n\x1b[33mShutting down servers...\x1b[0m');
  if (backend && !backend.killed) {
    if (isWindows) {
      spawn('taskkill', ['/pid', backend.pid.toString(), '/f', '/t'], { shell: true });
    } else {
      backend.kill('SIGTERM');
    }
  }
  if (frontend && !frontend.killed) {
    if (isWindows) {
      spawn('taskkill', ['/pid', frontend.pid.toString(), '/f', '/t'], { shell: true });
    } else {
      frontend.kill('SIGTERM');
    }
  }
  if (serenaFrontend && !serenaFrontend.killed) {
    if (isWindows) {
      spawn('taskkill', ['/pid', serenaFrontend.pid.toString(), '/f', '/t'], { shell: true });
    } else {
      serenaFrontend.kill('SIGTERM');
    }
  }
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
