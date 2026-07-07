import requests, sys, os, subprocess, time
sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, '..', 'src', 'backend')
PORT = 9000

try:
    r = requests.get(f'http://127.0.0.1:{PORT}/', timeout=3)
    print('Server already running')
except Exception:
    env = os.environ.copy()
    env['AI_API_KEY'] = os.environ.get('AI_API_KEY', '')
    env['AI_API_URL'] = os.environ.get('AI_API_URL', '')
    env['PYTHONIOENCODING'] = 'utf-8'
    p = subprocess.Popen(['python', 'app.py'], cwd=BASE_DIR,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    time.sleep(3)
    if p.poll() is not None:
        _, err = p.communicate()
        print(f'Server failed to start: {err.decode("utf-8", errors="replace")[:200]}')
        sys.exit(1)
    print('Server started')

r = requests.post(f'http://127.0.0.1:{PORT}/api/rpg/start',
    json={'world_id': 'misty-tavern', 'player_name': '测试'}, timeout=30)
data = r.json()
reply = data.get('reply', '')
print(f'Status: {r.status_code}')
print(f'Reply: {reply[:200]}')

if 'AI_API_KEY' in reply:
    print('\n!!! API未配置! 环境变量没传进去')
    print('请关闭所有python进程后, 重新双击start.bat启动')
elif r.status_code == 200:
    print('\nRPG 正常工作! AI GM已就绪')
    sid = data['session_id']
    r2 = requests.post(f'http://127.0.0.1:{PORT}/api/rpg/act',
        json={'session_id': sid, 'choice': '推门进去'}, timeout=30)
    if r2.status_code == 200:
        print(f'Choice response: {r2.json()["reply"][:150]}')
