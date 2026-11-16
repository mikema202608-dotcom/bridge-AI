"""AI 学习空间。使用 Python 3 标准库运行。"""
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SCHOOL_DATA', ROOT / 'data')).resolve()
PORT = int(os.environ.get('SCHOOL_PORT', '8766'))
BIND = os.environ.get('SCHOOL_BIND', '127.0.0.1')
ORIGIN = os.environ.get('SCHOOL_ORIGIN', f'http://127.0.0.1:{PORT}').rstrip('/')
ADMIN = os.environ.get('SCHOOL_ADMIN', 'mike')
MAX_SIZE = 50 * 1024 * 1024
VIDEO_TYPES = {'video/mp4', 'video/webm', 'video/quicktime'}
ID_PATH = re.compile(r'/api/videos/([a-f0-9]{32})')
MUTATION_LOCK = threading.Lock()
ATTEMPTS_LOCK = threading.Lock()
ATTEMPTS = []
TOKEN_KEY = secrets.token_bytes(32)
SALT = secrets.token_bytes(16)
HTML_HEADERS = {'Content-Security-Policy': "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"}

GUEST_PAGE = """
<section class="hero"><div class="orb"></div><div class="over">AI LEARNING STUDIO</div>
<h1>用自己的节奏，学习 AI。</h1><p>为家长准备的录播课程。选择一节课即可观看。</p>
<a class="button" href="#courses">查看课程</a></section>
<section id="player" class="panel" hidden></section>
<section id="courses"><div class="section"><div><h2>课程目录</h2><p>公开体验</p></div></div>
<div id="list" class="list" aria-live="polite">正在加载课程…</div></section>
"""
LOGIN_PAGE = """
<section class="panel signin"><div class="over">OWNER SIGN IN</div><h1>站长登录</h1>
<p>登录后进入视频管理工作室。</p>{message}
<form action="/login" method="post"><label class="label" for="username">站长账号</label>
<input id="username" name="username" type="text" autocomplete="username" required maxlength="128">
<label class="label" for="password">密码</label>
<input id="password" name="password" type="password" autocomplete="current-password" required maxlength="256">
<button>登录工作室</button></form></section>
"""
ADMIN_PAGE = """
<div class="over">OWNER STUDIO</div><h1>站长工作室</h1><p>上传录播视频，上传完成后会出现在访客版课程目录。</p>
<form class="panel" id="upload"><h2>上传视频</h2><label class="label" for="title">课程标题</label>
<input id="title" type="text" maxlength="100" required>
<label class="label" for="file">视频文件</label>
<input id="file" type="file" accept="video/mp4,video/webm,video/quicktime" required>
<p class="muted">支持 MP4、WebM 和 MOV。单个文件上限 50 MB，建议使用 MP4。</p>
<button>上传到课程目录</button><span id="status" class="status" role="status"></span></form>
<div class="section"><h2>已发布课程</h2><form action="/logout" method="post"><button class="ghost">退出登录</button></form></div>
<div id="list" class="list" aria-live="polite">正在加载课程…</div>
"""


def password_hash(value):
    return hashlib.pbkdf2_hmac('sha256', value.encode('utf-8'), SALT, 600_000)


def database():
    return sqlite3.connect(DATA / 'catalog.sqlite3')


def page(title, content, label, script=False):
    script_tag = '<script src="/client.js" defer></script>' if script else ''
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · AI 学习空间</title><link rel="stylesheet" href="/style.css">{script_tag}</head>
<body><div class="shell"><header class="mast"><a class="brand" href="/"><span class="logo">A</span>AI 学习空间</a>
<span class="muted">{label}</span></header><main class="page">{content}</main></div></body></html>"""


def token_signature(expiry, nonce):
    return hmac.new(TOKEN_KEY, f'{expiry}.{nonce}'.encode(), 'sha256').hexdigest()


class Site(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def send_bytes(self, body, content_type='text/plain; charset=utf-8', status=200, headers=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def render(self, title, content, label, script=False, status=200):
        self.send_bytes(page(title, content, label, script), 'text/html; charset=utf-8', status, HTML_HEADERS)

    def redirect(self, target, cookie=None):
        headers = {'Location': target}
        if cookie is not None:
            headers['Set-Cookie'] = cookie
        self.send_bytes('', status=303, headers=headers)

    def cookie(self, value, age):
        secure = '; Secure' if ORIGIN.startswith('https://') else ''
        return f'school_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}'

    def is_admin(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            expiry, nonce, signature = cookie['school_session'].value.split('.')
            return int(expiry) > time.time() and hmac.compare_digest(signature, token_signature(expiry, nonce))
        except (KeyError, ValueError):
            return False

    def length(self, max_size):
        try:
            value = int(self.headers.get('Content-Length', '0'))
            return value if 0 < value <= max_size else None
        except ValueError:
            return None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/', '/courses', '/watch'):
            self.render('课程', GUEST_PAGE, '访客版', True)
        elif path == '/login':
            if self.is_admin():
                self.redirect('/admin')
            else:
                self.render('站长登录', LOGIN_PAGE.format(message=''), '站长入口')
        elif path == '/admin':
            if self.is_admin():
                self.render('视频管理', ADMIN_PAGE, '管理者版', True)
            else:
                self.redirect('/login')
        elif path == '/style.css':
            self.send_bytes((ROOT / 'style.css').read_bytes(), 'text/css; charset=utf-8')
        elif path == '/client.js':
            self.send_bytes((ROOT / 'client.js').read_bytes(), 'text/javascript; charset=utf-8')
        elif path == '/api/videos':
            with database() as db:
                videos = db.execute('SELECT id, title FROM videos ORDER BY rowid DESC').fetchall()
            self.send_bytes(json.dumps([{'id': key, 'title': title} for key, title in videos],
                                       ensure_ascii=False), 'application/json; charset=utf-8')
        elif match := ID_PATH.fullmatch(path):
            self.video(match[1])
        else:
            self.send_bytes('页面不存在。', status=404)

    do_HEAD = do_GET

    def do_POST(self):
        if self.headers.get('Origin') != ORIGIN:
            self.send_bytes('请从网站页面重新提交。', status=403)
            return
        path = urlsplit(self.path).path
        if path == '/login':
            self.login()
        elif not self.is_admin():
            self.send_bytes('请先用站长账号登录。', status=403)
        elif path == '/logout':
            self.redirect('/login', self.cookie('', 0))
        elif path == '/api/videos':
            self.upload()
        else:
            self.send_bytes('页面不存在。', status=404)

    def login(self):
        length = self.length(8192)
        if length is None:
            self.send_bytes('登录请求不正确。', status=400)
            return
        with ATTEMPTS_LOCK:
            cutoff = time.monotonic() - 60
            ATTEMPTS[:] = [value for value in ATTEMPTS if value > cutoff]
            if len(ATTEMPTS) >= 15:
                self.send_bytes('登录尝试过多，请稍等一分钟。', status=429)
                return
            ATTEMPTS.append(time.monotonic())
        form = parse_qs(self.rfile.read(length).decode('utf-8', 'replace'))
        name = form.get('username', [''])[0]
        value = form.get('password', [''])[0]
        valid = len(value) <= 256 and hmac.compare_digest(password_hash(value), self.server.admin_hash)
        if not valid or not hmac.compare_digest(name.encode(), ADMIN.encode()):
            message = '<p class="error" role="alert">账号或密码不正确。</p>'
            self.render('站长登录', LOGIN_PAGE.format(message=message), '站长入口', status=401)
            return
        age = 8 * 3600
        expiry = str(int(time.time()) + age)
        nonce = secrets.token_hex(16)
        self.redirect('/admin', self.cookie(f'{expiry}.{nonce}.{token_signature(expiry, nonce)}', age))

    def upload(self):
        length = self.length(MAX_SIZE)
        mime = self.headers.get('Content-Type', '')
        title = unquote(self.headers.get('X-Video-Title', '')).strip()
        if length is None or mime not in VIDEO_TYPES or not 1 <= len(title) <= 100:
            self.send_bytes('请填写标题并选择不超过 50 MB 的 MP4、WebM 或 MOV 视频。', status=400)
            return
        key = secrets.token_hex(16)
        path = DATA / key
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=DATA, delete=False) as stream:
                tmp_path = Path(stream.name)
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        raise OSError('incomplete upload')
                    stream.write(chunk)
                    remaining -= len(chunk)
            with MUTATION_LOCK:
                tmp_path.replace(path)
                try:
                    with database() as db:
                        db.execute('INSERT INTO videos VALUES (?, ?, ?)', (key, title, mime))
                except sqlite3.Error:
                    path.unlink(missing_ok=True)
                    raise
        except (OSError, sqlite3.Error):
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            self.send_bytes('视频未保存，请重试。', status=500)
            return
        self.send_bytes('已上传。', status=201)

    def do_DELETE(self):
        if not self.is_admin() or self.headers.get('Origin') != ORIGIN:
            self.send_bytes('只有站长可以删除课程。', status=403)
            return
        match = ID_PATH.fullmatch(urlsplit(self.path).path)
        if not match:
            self.send_bytes('课程不存在。', status=404)
            return
        key = match[1]
        with MUTATION_LOCK:
            with database() as db:
                deleted = db.execute('DELETE FROM videos WHERE id=?', (key,)).rowcount
            if deleted:
                (DATA / key).unlink(missing_ok=True)
        self.send_bytes('已删除。')

    def video(self, key):
        with MUTATION_LOCK:
            with database() as db:
                row = db.execute('SELECT mime FROM videos WHERE id=?', (key,)).fetchone()
            try:
                stream = (DATA / key).open('rb') if row else None
            except FileNotFoundError:
                stream = None
        if stream is None:
            self.send_bytes('课程不存在。', status=404)
            return
        with stream:
            size = os.fstat(stream.fileno()).st_size
            start, end = 0, size - 1
            requested = self.headers.get('Range', '')
            if requested:
                parts = re.fullmatch(r'bytes=([0-9]{0,16})-([0-9]{0,16})', requested)
                if parts and parts[1]:
                    start = int(parts[1])
                    if parts[2]:
                        end = min(end, int(parts[2]))
                elif parts and parts[2] and int(parts[2]) > 0:
                    start = max(0, size - int(parts[2]))
                else:
                    start = size
                if start > end:
                    self.send_bytes('请求的视频片段不存在。', status=416,
                                    headers={'Content-Range': f'bytes */{size}'})
                    return
            length = end - start + 1
            self.send_response(206 if requested else 200)
            self.send_header('Content-Type', row[0])
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if requested:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            stream.seek(start)
            while length:
                chunk = stream.read(min(length, 65536))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                length -= len(chunk)


def main():
    secret = os.environ.pop('SCHOOL_PASSWORD', None) or getpass.getpass('设置站长密码（至少 12 个字符）：')
    if not 12 <= len(secret) <= 256:
        raise SystemExit('请设置 12 至 256 个字符的站长密码。')
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    with database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS videos (id TEXT PRIMARY KEY, title TEXT NOT NULL, mime TEXT NOT NULL)')
    with ThreadingHTTPServer((BIND, PORT), Site) as server:
        server.admin_hash = password_hash(secret)
        del secret
        print(f'访客版 {ORIGIN}/\n站长登录 {ORIGIN}/login\n视频管理 {ORIGIN}/admin', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
