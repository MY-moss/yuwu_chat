import os, subprocess, time, sys
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, '..', 'src', 'backend')
env = os.environ.copy()
env['AI_API_KEY'] = 'public'
env['AI_API_URL'] = 'https://opencode.ai/zen/v1/chat/completions'
env['PYTHONIOENCODING'] = 'utf-8'

print(f"Starting fresh server from: {BASE_DIR}")
print(f"AI: opencode.ai/zen (free)")
print()

p = subprocess.Popen(['python', 'app.py'], cwd=BASE_DIR,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True, bufsize=1)

def log_output():
    try:
        for line in p.stdout:
            print(f"[SERVER] {line.rstrip()}")
    except:
        pass

import threading
t = threading.Thread(target=log_output, daemon=True)
t.start()

time.sleep(3)

import requests

try:
    r = requests.get('http://127.0.0.1:9000/', timeout=5)
    print(f'\nSERVER: {r.status_code}')
except requests.exceptions.RequestException as e:
    print(f'\n[SERVER] Failed to connect: {e}')
    print('[SERVER] Exiting...')
    p.terminate()
    p.wait()
    sys.exit(1)

try:
    r = requests.post('http://127.0.0.1:9000/api/rpg/start',
        json={'world_id': 'misty-tavern', 'player_name': '游侠'}, timeout=30)
    data = r.json()
    reply = data.get('reply', '')
    print(f'RPG Start: {r.status_code}')
    print(f'Reply: {reply[:150]}')

    if 'AI_API_KEY' in reply:
        print('\n!!! 配置失败')
    else:
        print(f'\nRPG OK! Session: {data.get("session_id","?")}')
except requests.exceptions.RequestException as e:
    print(f'\n[RPG] Test failed: {e}')

print('\nServer running at http://127.0.0.1:9000')
print('Press Ctrl+C to stop...')
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print('\nStopping server...')
    p.terminate()
    p.wait()
    print('Server stopped')