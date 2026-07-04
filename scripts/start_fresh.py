import os, subprocess, time, sys
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, '..', 'src', 'backend')
env = os.environ.copy()
env['AI_API_KEY'] = 'public'
env['AI_API_URL'] = 'https://opencode.ai/zen/v1/chat/completions'
env['PYTHONIOENCODING'] = 'utf-8'

p = subprocess.Popen(['python', 'app.py'], cwd=BASE_DIR,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
time.sleep(3)

import requests
r = requests.get('http://127.0.0.1:9000/', timeout=5)
print(f'SERVER: {r.status_code}')

# Test RPG
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

# Keep running for user
print('\nServer running at http://127.0.0.1:9000')
print('Press Ctrl+C to stop...')
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    p.terminate()
    p.wait()
    print('Server stopped')
