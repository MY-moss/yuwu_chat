import os, subprocess, time, sys, requests
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, '..', 'src', 'backend')
env = os.environ.copy()
env['AI_API_KEY'] = 'public'
env['AI_API_URL'] = 'https://opencode.ai/zen/v1/chat/completions'
env['PYTHONIOENCODING'] = 'utf-8'

print(f"Starting server from: {BASE_DIR}")
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

try:
    r = requests.get('http://127.0.0.1:9000/', timeout=5)
    print(f'\nSERVER: {r.status_code} OK')
    print(f'URL: http://127.0.0.1:9000')
except requests.exceptions.RequestException as e:
    print(f'\n[SERVER] Failed to connect: {e}')
    print('[SERVER] Checking server output for errors...')

try:
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    print('\nShutting down...')
    p.terminate()
    p.wait()