# Complete Setup & Installation Guide

This guide explains how to set up and run the **Tamil Nadu Electoral Roll OCR Workspace** on any PC after cloning from GitHub.

---

## ⚡ Prerequisites

| Requirement | Recommended Version | Notes |
| :--- | :--- | :--- |
| **Node.js** | `20.x` or newer | Includes `npm` for the frontend and workspace scripts |
| **Python** | `3.11` (or `3.10` / `3.12`) | Installed automatically on Windows if missing |
| **RAM** | `8 GB+` (16 GB recommended) | CPU inference uses ~1.5 GB RAM per OCR worker |
| **Disk Space** | `~3–4 GB` free | For Python packages, PaddleOCR models, and node_modules |

---

## 🪟 Windows Setup (Easiest)

### Method 1: 1-Click Batch (Recommended)
1. Clone the repository:
   ```cmd
   git clone https://github.com/mukeshkannanduraisamy-hue/tn-electoral-roll-ocr.git OCR
   cd OCR
   ```
2. Double-click `setup.bat` (or run `setup.bat` in Command Prompt / PowerShell).
   - *This automatically detects/installs Python 3.11, creates the virtualenv, installs dependencies, downloads OCR models, sets up `.env`, and installs npm packages.*
3. Double-click `run.bat` (or run `run.bat`).
4. Open your browser:
   - **Frontend UI:** [http://localhost:3000](http://localhost:3000)
   - **Backend Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Default Admin Login:** Username `admin` | Password `Admin@123456`

### Method 2: PowerShell
```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
npm run dev
```

---

## 🐧 Linux / Ubuntu / Debian / WSL Setup

### 1. Install System Prerequisites
On Ubuntu / Debian:
```bash
sudo apt update && sudo apt install -y \
    python3.11 python3.11-venv python3-pip \
    nodejs npm \
    libgl1 libgomp1 fonts-noto-core curl
```

### 2. 1-Click Setup & Run
```bash
git clone https://github.com/mukeshkannanduraisamy-hue/tn-electoral-roll-ocr.git OCR
cd OCR

# Run Setup
chmod +x setup.sh run.sh scripts/*.sh
./setup.sh

# Start Application
./run.sh
```

---

## 🍎 macOS Setup

1. Install prerequisites via Homebrew:
   ```bash
   brew install python@3.11 node
   ```
2. Setup and run:
   ```bash
   git clone https://github.com/mukeshkannanduraisamy-hue/tn-electoral-roll-ocr.git OCR
   cd OCR
   chmod +x setup.sh run.sh scripts/*.sh
   ./setup.sh
   ./run.sh
   ```

---

## 🐳 Docker Setup (No Local Python/Node Needed)

If you have Docker Desktop or Docker Engine installed:

```bash
git clone https://github.com/mukeshkannanduraisamy-hue/tn-electoral-roll-ocr.git OCR
cd OCR

# Start both backend and frontend in containers:
docker compose up --build
```

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend: [http://localhost:8000/docs](http://localhost:8000/docs)

### Docker with NVIDIA GPU Acceleration
If you have an NVIDIA card and NVIDIA Container Toolkit installed:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

---

## ⚙️ Environment Configuration (`.env`)

A `.env` file is created automatically from `.env.example` during setup.

All settings have working defaults out-of-the-box:
- **Database:** Local SQLite database stored in `./data/ocr.sqlite`. Zero setup required.
- **OCR Engine:** CPU mode by default (`OCR_OCR_DEVICE=cpu`, `OCR_OCR_LANG=ta`, `OCR_OCR_VERSION=PP-OCRv5`).
- **AI Copilot (Optional):** To enable LLM-powered voter queries and insights, add your NVIDIA API key in `.env`:
  ```env
  NVIDIA_API_KEY=nvapi-...
  NVIDIA_MODEL=z-ai/glm-5.2
  ```
  *(If left blank, the app gracefully falls back to the offline rule engine).*

---

## 🧪 Testing & Verification

To verify that your installation is working properly:

```bash
# Run backend tests
npm run test:backend

# Verify web type safety
npm run test:web

# Test web production build
npm run build:web
```

To test CLI extraction on a PDF:
- **Windows:**
  ```cmd
  apps\api\.venv\Scripts\python.exe apps\api\cli.py extract "path\to\electoral_roll.pdf"
  ```
- **Linux / macOS:**
  ```bash
  apps/api/.venv/bin/python apps/api/cli.py extract "path/to/electoral_roll.pdf"
  ```

---

## ❓ Troubleshooting

### 1. PowerShell Execution Policy Restriction on Windows
If PowerShell gives an error about execution policy:
Run `setup.bat` and `run.bat` instead, or run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 2. OpenCV / Paddle ImportError on Linux (`libGL.so.1` or `libgomp.so.1`)
Install the required system shared libraries:
```bash
sudo apt update && sudo apt install -y libgl1 libgomp1
```

### 3. Missing Tamil Glyphs in Exported PDFs
Install Noto Tamil fonts:
- **Ubuntu/Debian:** `sudo apt install -y fonts-noto-core`
- **Windows:** Nirmala UI font (`C:/Windows/Fonts/Nirmala.ttc`) is already included in Windows 10/11.

### 4. Port Conflicts (Port 8000 or 3000 in use)
- You can change the backend port with:
  `uvicorn app.main:app --port 8001`
  and set `NEXT_PUBLIC_API_URL=http://localhost:8001` in `.env`.
- You can change the frontend port with:
  `npm run dev -- -p 3001`
