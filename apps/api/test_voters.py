import requests

s = requests.Session()
s.post('http://127.0.0.1:8000/api/auth/login', json={'username': 'admin', 'password': 'Admin@123456'})

r = s.get('http://127.0.0.1:8000/api/voters?sort=created_at&order=desc&offset=0&limit=50', timeout=30)
print('Voter list status:', r.status_code)
if r.status_code == 200:
    data = r.json()
    print('Total voters:', data.get('total', 0))
    items = data.get('items', [])
    print('Returned:', len(items))
    if items:
        v = items[0]
        print('Sample voter:', v.get('name'), '| age:', v.get('age'), '| epic:', v.get('epic'))
else:
    print('ERROR:', r.text[:500])
