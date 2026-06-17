import urllib.request, json
req = urllib.request.Request(
    'http://localhost:8000/queues/50428f38-909c-44d7-87c5-a6d7ed5c0f0e/tokens',
    data=b'{"phone": "1234567890"}',
    headers={'Content-Type': 'application/json'},
    method='POST'
)
try:
    print(urllib.request.urlopen(req).read().decode())
except Exception as e:
    print(e.read().decode())
