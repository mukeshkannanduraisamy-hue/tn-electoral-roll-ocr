import requests

s = requests.Session()
r = s.post('http://127.0.0.1:8000/api/auth/login', json={'username': 'admin', 'password': 'Admin@123456'})
print('Login:', r.status_code)

pages_r = s.get('http://127.0.0.1:8000/api/files/febccb7b24ad/pages')
pages = pages_r.json()
print('Total pages:', len(pages))

for p in pages:
    count = p.get('record_count', 0)
    if count > 0:
        page_id = p['id']
        print(f'Promoting page {page_id} with {count} records...')
        try:
            rp = s.post(
                'http://127.0.0.1:8000/api/voters/promote',
                json={'page_id': page_id, 'on_conflict': 'skip'},
                timeout=120,
            )
            print('Status:', rp.status_code)
            print('Response:', rp.text[:1000])
        except Exception as e:
            print('CLIENT ERROR:', type(e).__name__, str(e))
        break
