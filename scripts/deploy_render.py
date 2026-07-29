import os
import sys
import time
import httpx

API_KEY = "rnd_rPRa3Tpy4dhmQt8W4QoSCbLXONFA"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

API_SERVICE_ID = "srv-d9jimfnavr4c73ckclg0"
WEB_SERVICE_ID = "srv-d9jimfnavr4c73ckclf0"

def update_services():
    print("1. Updating API Service configuration...")
    api_payload = {
        "serviceDetails": {
            "healthCheckPath": "/api/health",
            "envSpecificDetails": {
                "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt",
                "startCommand": "sh -c \"uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1\"",
            },
        }
    }
    r = httpx.patch(f"https://api.render.com/v1/services/{API_SERVICE_ID}", headers=HEADERS, json=api_payload)
    print(f"API Service Patch Status: {r.status_code}")

    print("2. Updating Web Service configuration...")
    web_payload = {
        "serviceDetails": {
            "healthCheckPath": "/",
            "envSpecificDetails": {
                "buildCommand": "cd .. && npm ci && npm run build --workspace @ocr-workspace/web",
                "startCommand": "npm run start",
            },
        }
    }
    r = httpx.patch(f"https://api.render.com/v1/services/{WEB_SERVICE_ID}", headers=HEADERS, json=web_payload)
    print(f"Web Service Patch Status: {r.status_code}")

def trigger_deploys():
    print("3. Triggering deployment for API...")
    r1 = httpx.post(f"https://api.render.com/v1/services/{API_SERVICE_ID}/deploys", headers=HEADERS)
    d1 = r1.json() if r1.status_code == 201 else {}
    print(f"API Deploy Trigger: {r1.status_code}, Deploy ID: {d1.get('id')}")

    print("4. Triggering deployment for Web...")
    r2 = httpx.post(f"https://api.render.com/v1/services/{WEB_SERVICE_ID}/deploys", headers=HEADERS)
    d2 = r2.json() if r2.status_code == 201 else {}
    print(f"Web Deploy Trigger: {r2.status_code}, Deploy ID: {d2.get('id')}")

    return d1.get("id"), d2.get("id")

def monitor(api_deploy_id, web_deploy_id):
    print("5. Monitoring deployment progress...")
    for iteration in range(20):
        time.sleep(15)
        r_api = httpx.get(f"https://api.render.com/v1/services/{API_SERVICE_ID}/deploys/{api_deploy_id}", headers=HEADERS).json()
        r_web = httpx.get(f"https://api.render.com/v1/services/{WEB_SERVICE_ID}/deploys/{web_deploy_id}", headers=HEADERS).json()
        
        api_status = r_api.get("status")
        web_status = r_web.get("status")
        print(f"[{iteration*15}s] API: {api_status} | Web: {web_status}")

        if api_status in ["live", "deactivated", "build_failed", "update_failed"] and web_status in ["live", "deactivated", "build_failed", "update_failed"]:
            print(f"Final Status -> API: {api_status}, Web: {web_status}")
            break

if __name__ == "__main__":
    update_services()
    dep_api, dep_web = trigger_deploys()
    if dep_api and dep_web:
        monitor(dep_api, dep_web)
