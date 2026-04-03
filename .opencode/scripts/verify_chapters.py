import urllib.request
import json

resp = urllib.request.urlopen('http://127.0.0.1:8765/api/chapters')
data = json.loads(resp.read())
print(f'Chapters count: {len(data)}')
print(f'Chapter numbers: {[c["chapter"] for c in data]}')
