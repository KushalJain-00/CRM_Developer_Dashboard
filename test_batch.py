import urllib.request, json

data = json.dumps({
    'file_name': 'test',
    'sheet_name': 'test',
    'mapping': {},
    'contacts': []
}).encode()

req = urllib.request.Request(
    'https://crm-developer-dashboard.onrender.com/api/contacts/batch',
    data=data,
    method='POST'
)
req.add_header('Content-Type', 'application/json')
req.add_header('Origin', 'https://crmdevloper.vercel.app')

try:
    resp = urllib.request.urlopen(req)
    print('Status:', resp.status)
    print('Body:', resp.read().decode()[:500])
except urllib.error.HTTPError as e:
    print('Status:', e.code)
    print('CORS header:', e.headers.get('access-control-allow-origin', 'MISSING'))
    print('Body:', e.read().decode()[:500])
