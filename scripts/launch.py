import os, subprocess, time, sys, requests
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

r = requests.get('http://127.0.0.1:9000/', timeout=5)
print(f'SERVER: {r.status_code} OK')
print(f'URL: http://127.0.0.1:9000')
print(f'AI: opencode.ai/zen (free)')

# Keep alive
try:
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    p.terminate()
    p.wait()
