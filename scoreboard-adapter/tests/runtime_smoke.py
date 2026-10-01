#!/usr/bin/env python3
"""Isolated P2.3B runtime smoke; Python stdlib, never production."""
import copy
import json
import pathlib
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

CACHE = pathlib.Path('/home/ubuntu/.cache/scoreboard-p23b')
IMAGE = 'bjj-scoreboard:p2.3b-test'
BASE = 'http://127.0.0.1:39000'
NAME = 'scoreboard-p23b-' + uuid.uuid4().hex[:10]
NETWORK = NAME + '-net'
EVIDENCE = CACHE / 'runtime-evidence.json'
report = {'image': IMAGE, 'container': NAME, 'network': NETWORK, 'requests': [], 'polling': [], 'checks': []}

def docker(*args, check=True):
    p = subprocess.run(['docker', *args], text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr)
    return p

def check(condition, label):
    assert condition, label
    report['checks'].append(label)

def request(path, method='GET', body=None, timeout=3, raw=False):
    if body is not None and not raw:
        body = json.dumps(body).encode()
    elif isinstance(body, str):
        body = body.encode()
    headers = {'Content-Type': 'text/plain' if raw else 'application/json'}
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        r = e
    with r:
        data = r.read().decode()
        status = r.status
    try:
        parsed = json.loads(data)
    except ValueError:
        parsed = data
    report['requests'].append({'method': method, 'path': path, 'status': status, 'response': parsed})
    return status, parsed

class Client:
    def __init__(self):
        status, opening = request('/socket.io/?EIO=4&transport=polling')
        check(status == 200 and opening.startswith('0'), 'Engine.IO handshake polling 200')
        self.sid = json.loads(opening[1:])['sid']
        self.path = '/socket.io/?EIO=4&transport=polling&sid=' + self.sid
        check(request(self.path, 'POST', '40', raw=True)[0] == 200, 'Socket.IO namespace connect 200')
    def poll(self, timeout=3):
        status, packets = request(self.path, timeout=timeout)
        check(status == 200, 'Socket.IO poll 200')
        packets = packets.split('\x1e') if '\x1e' in packets else packets.split(chr(30))
        report['polling'].append({'sid': self.sid, 'packets': packets})
        return [json.loads(p[2:]) for p in packets if p.startswith('42')]
    def send(self, event, payload):
        check(request(self.path, 'POST', '42' + json.dumps([event, payload]), raw=True)[0] == 200, event + ' sent')

assignment = {
    'tournament_id': 7, 'match_id': 40, 'tatami_id': 1,
    'fighter_a': {'stage_item_input_id': 1, 'team_id': 101, 'name': 'Ana', 'club': None},
    'fighter_b': {'stage_item_input_id': 2, 'team_id': 102, 'name': 'Bea', 'club': None},
    'category': {'stage_item_id': 9, 'name': 'Adult'}, 'duration_seconds': 300,
}
network_created = container_created = False
try:
    CACHE.mkdir(parents=True, exist_ok=True)
    # Fail before creating resources if the required localhost port is in use.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 39000))
    report['image_id'] = docker('image', 'inspect', IMAGE, '--format', '{{.Id}}').stdout.strip()
    docker('network', 'create', NETWORK)
    network_created = True
    docker('run', '-d', '--name', NAME, '--network', NETWORK, '--user', 'node',
           '-p', '127.0.0.1:39000:3000', '-e', 'SCOREBOARD_MODE=integrated', IMAGE)
    container_created = True
    own = json.loads(docker('inspect', NAME).stdout)[0]
    report['runtime_config'] = {
        'user': own['Config']['User'], 'env': own['Config']['Env'],
        'cmd': own['Config']['Cmd'], 'privileged': own['HostConfig']['Privileged'],
        'cap_add': own['HostConfig']['CapAdd'], 'mounts': own['Mounts'],
        'networks': list(own['NetworkSettings']['Networks']),
        'ports': own['HostConfig']['PortBindings'],
    }
    check(own['Config']['User'] == 'node', 'runtime user node')
    check(not own['HostConfig']['Privileged'] and not own['HostConfig']['CapAdd'], 'no privileged/cap-add')
    check(not own['Mounts'] and list(own['NetworkSettings']['Networks']) == [NETWORK], 'no mounts, dedicated network only')
    check(own['HostConfig']['PortBindings'] == {'3000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '39000'}]}, 'localhost-only port binding')
    check('SCOREBOARD_MODE=integrated' in own['Config']['Env'], 'explicit integrated mode')
    for _ in range(60):
        try:
            if request('/internal/tatamis/1/state') == (200, {'state': None}):
                break
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.1)
    else:
        raise RuntimeError('runtime not ready')
    check(request('/internal/tatamis/1/state') == (200, {'state': None}), 'empty GET state null')
    for path in ['/', '/control', '/control2', '/js/main.js', '/socket.io/socket.io.js']:
        check(request(path)[0] == 200, 'legacy route 200 ' + path)
    a = Client()
    check(a.poll() == [], 'empty connection emits no snapshot')
    status, first = request('/internal/tatamis/1/assignment', 'PUT', assignment)
    check(status == 201, 'new PUT 201')
    state = first['state']
    expected = copy.deepcopy(assignment)
    for fighter in ('fighter_a', 'fighter_b'):
        expected[fighter].update(points=0, advantages=0, penalties=0)
    expected.update(remaining_seconds=300, status='ready', winner_team_id=None, method=None,
                    session_id=state['session_id'], revision=1)
    check(state == expected and uuid.UUID(state['session_id']).version == 4, 'exact ready snapshot and UUID v4')
    check(a.poll() == [['tatami:state', state]], 'new assignment broadcasts snapshot')
    check(request('/internal/tatamis/1/state') == (200, first), 'GET exact snapshot')
    reordered = dict(reversed(list(assignment.items())))
    reordered['fighter_a'] = dict(reversed(list(assignment['fighter_a'].items())))
    check(request('/internal/tatamis/1/assignment', 'PUT', reordered) == (200, first), 'reordered replay PUT 200 same session/state')
    check(a.poll() == [['tatami:state', state]], 'idempotent assignment broadcasts snapshot')
    b = Client()
    check(b.poll() == [['tatami:state', state]], 'new connection receives active snapshot')
    for label, changed in [('same-match', {'duration_seconds': 301}), ('other-match', {'match_id': 41})]:
        payload = {**assignment, **changed}
        check(request('/internal/tatamis/1/assignment', 'PUT', payload)[0] == 409, label + ' PUT conflict 409')
    check(request('/internal/tatamis/1/assignment', 'PUT', {**assignment, 'extra': True})[0] == 400, 'invalid payload 400 even when assigned')
    for event in ('bjj:score', 'bjj:start', 'bjj:restart'):
        payload = {'synthetic': event, 'nested': {'score': 99}}
        a.send(event, payload)
        check(a.poll() == [[event, payload]], event + ' includes sender, no extra events')
        check(b.poll() == [[event, payload]], event + ' reaches peer, no extra events')
    check(request('/internal/tatamis/1/state') == (200, first), 'legacy broadcasts do not mutate state')
    a.send('bjj:name', {'name': 'Synthetic'})
    check(b.poll() == [['bjj:name', {'name': 'Synthetic'}]], 'bjj:name reaches peer')
    try:
        a.poll(timeout=.4)
    except (TimeoutError, socket.timeout):
        check(True, 'bjj:name excludes sender; no tatami:update')
    else:
        raise AssertionError('unexpected sender event after bjj:name')
    files = docker('exec', NAME, 'node', '-e', "console.log(JSON.stringify(require('node:fs').readdirSync('/app/scoreboard-adapter').sort()))").stdout
    check(json.loads(files) == ['integrated.js', 'launcher.js', 'state.js'], 'image excludes adapter tests/docs')
    report['result'] = 'PASS'
except BaseException as exc:
    report['result'] = 'FAIL'
    report['error'] = repr(exc)
    raise
finally:
    if container_created:
        (CACHE / 'runtime-container.log').write_text(docker('logs', NAME, check=False).stdout)
        docker('rm', '-f', NAME, check=False)
    if network_created:
        docker('network', 'rm', NETWORK, check=False)
    report['cleanup'] = {
        'container_absent': docker('inspect', NAME, check=False).returncode != 0,
        'network_absent': docker('network', 'inspect', NETWORK, check=False).returncode != 0,
    }
    EVIDENCE.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': report.get('result'), 'image_id': report.get('image_id'),
                      'checks': len(report['checks']), 'cleanup': report['cleanup'],
                      'evidence': str(EVIDENCE)}, indent=2))
    assert all(report['cleanup'].values()), 'cleanup incomplete'
