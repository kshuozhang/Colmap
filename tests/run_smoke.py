"""Submit the generated sample through the real running app's HTTP API."""
import json
from pathlib import Path
import time
import urllib.request

BASE='http://127.0.0.1:8765'
ROOT=Path(__file__).resolve().parents[1]


def request(path,data=None,headers=None):
    with urllib.request.urlopen(urllib.request.Request(BASE+path,data=data,headers=headers or {})) as response:
        return json.load(response)


token=request('/api/info')['token']
headers={'X-Head-Studio-Token':token}
project=request('/api/projects',json.dumps({'name':'Integration sample — textured ellipsoid','preset':'draft'}).encode(),headers)
identifier=project['id']
(ROOT/'.test-data/smoke-project.txt').write_text(identifier)
for photo in sorted((ROOT/'.test-data/capture').glob('*.png')):
    request('/api/projects/'+identifier+'/photos',photo.read_bytes(),dict(headers,**{'X-Filename':photo.name}))
request('/api/projects/'+identifier+'/start',b'{}',headers)
last=None
while True:
    state=request('/api/projects/'+identifier)
    marker=(state['state'],state['step'])
    if marker!=last:
        print(state['state'],state['step'],state['message'],flush=True)
        last=marker
    if state['state']!='running':
        print(json.dumps(state,indent=2),flush=True)
        if state['state']!='complete':raise SystemExit(1)
        break
    time.sleep(3)
