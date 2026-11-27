"""프로밀리아 가이드 트래커 (2026-11-26 · 예전 이름: 맵스 트래커 2) — 게임 메모리를 읽지 않는 화면 인식 방식

게임 화면 왼쪽 위의 미니맵을 캡처해서 프로밀리아 가이드 지도 그림과 맞춰 위치를 찾고(locator.py),
기존 트래커와 같은 웹소켓(ws://127.0.0.1:46822 · 같은 메시지 형식)으로 사이트 지도(/map 「내 위치」)에 보냄 — 사이트는 그대로 씀.
- 게임 프로세스에 접근하지 않음(메모리 읽기 · 주입 없음) · 관리자 권한이 필요 없음 · 화면을 다른 곳으로 보내지 않음
- 게임 창이 화면에 보여야 함(가려지거나 최소화되면 못 읽음) · 메뉴 · 지도 · 연출 화면에서는 위치를 잠시 놓침
- 정확도는 약 1m · 초당 5~10번 · 높이는 지형 높이(건물 위 · 공중은 반영 안 됨)
- 관측 기록: 게임의 관측 기록 화면을 글자 인식(OCR)으로 읽어 모음 (gacha_ocr.py)
- 예전 트래커(promilia-tracker · 메모리 방식 · 이제 안 씀)와 같은 포트를 쓰므로 둘을 같이 켤 수 없음
지도 자료는 처음 실행할 때 사이트에서 받아 exe 옆 maps/ 에 보관 · 설정은 promilia-tracker2.json
"""
import asyncio, base64, hashlib, json, os, struct, sys, time, threading
import ctypes, ctypes.wintypes as W
import diag

APP = '프로밀리아 가이드 트래커'
VER = '2.1.2'   # 11-28: 덜 뚜렷한 후보도 두 번 연속 같은 자리면 붙음 (3440×1440 진단) · 2.1.1: 미니맵 테두리 오인식 거르기 · 기본 자리 번갈아 시험
PORT = 46822
MAP_URL = 'https://azprguide.xyz/map'   # 11-27: 사이트 새 주소 (지도 자료는 locator.py 가 받음)
# 새 버전 안내 (updater.py · 11-27): 이 저장소 Releases 에서 앞말 없는 태그(2.1.0 · v2.1.0)만 이 트래커의 새 버전으로 봄 — 메모리 트래커는 'mem-' 태그
REPO = 'azprguide/promilia-tracker'
TAG_PREFIX = ''
ORIGINS = ('https://azur-promilia.pages.dev', 'https://azprguide.xyz', 'https://www.azprguide.xyz', 'http://localhost:8791', 'http://127.0.0.1:8791')   # 11-27: 새 도메인 azprguide.xyz 추가   # 이 사이트에서만 연결 허용
WINDOW_TITLE = 'AzurPromilia'
HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
CFG_PATH = os.path.join(HERE, 'promilia-tracker2.json')
u32 = ctypes.windll.user32
u32.FindWindowW.restype = W.HWND; u32.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]


class St:
    game = 'off'             # off · on
    state = 'idle'           # idle · nogame · search · lock
    msg = '시작하는 중…'
    pos = None
    since = 0.0
    city = None
    score = 0.0
    gacha_count = 0
    gacha_status = ''
    debug = ''
    clients = 0
    server = 'off'           # off · on · error
    error = ''
    reacquire = threading.Event()
    reconnect = threading.Event()
    quit = False
    cfg = {'auto': True}
    hwnd = None


def load_cfg():
    try:
        St.cfg.update(json.load(open(CFG_PATH, encoding='utf-8')))
    except Exception:
        pass


def save_cfg():
    try:
        json.dump(St.cfg, open(CFG_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception:
        pass


def setstate(s, msg=''):
    St.state, St.msg = s, msg


def game_rect():
    """게임 창의 화면 안쪽 영역 (x, y, w, h) — 없거나 최소화면 None"""
    h = u32.FindWindowW(None, WINDOW_TITLE); St.hwnd = h
    if not h or u32.IsIconic(h):
        return None
    rc = W.RECT(); pt = W.POINT(0, 0)
    if not u32.GetClientRect(h, ctypes.byref(rc)) or not u32.ClientToScreen(h, ctypes.byref(pt)) or rc.bottom < 300:
        return None
    return pt.x, pt.y, rc.right, rc.bottom


def worker():
    import capture
    import locator
    try:
        loc = locator.Locator(os.path.join(HERE, 'maps'), lambda s: setstate('idle', s), float(St.cfg.get('px_per_m') or locator.MM_PX_PER_M))
    except Exception as e:
        St.error = f'지도 자료를 받지 못했어요 (인터넷 연결 확인): {type(e).__name__}'; setstate('idle', '지도 자료 없음'); diag.log('maps', ok=False, err=f'{type(e).__name__}: {e}'); return
    diag.log('maps', ok=True, maps=[f'{m.name}({m.id}) tex={m.tex} size={m.size[0]:.0f}m ppm={loc.ppm(m):.2f}' for m in loc.maps])
    names = {m.id: m.name for m in loc.maps}
    St.scenes = names
    miss = 0; t_lock = 0.0; wsize = None
    while not St.quit:
        t0 = time.time()
        if St.reacquire.is_set() or St.reconnect.is_set():
            St.reacquire.clear(); St.reconnect.clear(); loc.cur = None
        r = game_rect()
        diag.game(getattr(St, 'hwnd', None), r)
        if not r:
            St.game = 'off'; St.pos = None; loc.cur = None; setstate('nogame', '게임 창을 찾는 중…'); time.sleep(1); continue
        St.game = 'on'; x, y, w, h = r
        if (w, h) != wsize or miss % 40 == 12:                         # 창 크기가 바뀌었거나 오래 못 찾으면 미니맵 테두리를 다시 찾음 (21:9 등)
            wsize = (w, h)
            try:
                g, sc = loc.detect(lambda b: capture.grab((x + b[0], y + b[1], x + b[2], y + b[3])), w, h)
                St.debug = f'미니맵 자리 {g} (테두리 {sc:.2f})' if g else f'미니맵 테두리를 못 찾아 기본 자리를 씀 ({sc:.2f})'
                diag.log('ring', w=w, h=h, ratio=diag.ratio(w, h), found=bool(g), geom=[int(v) for v in g] if g else None, score=round(sc, 3), crop=list(loc.crop_box(w, h)),
                         cand=loc.cand, expect=[[round(v) for v in e] for e in loc.expected(w, h)], win=[x, y, w, h])   # 11-28: 후보 · 버린 이유 · 예상 자리 · 게임 창
            except Exception as e:
                loc.geom = None; St.debug = f'미니맵 자리 찾기 실패: {type(e).__name__}'; diag.log('error', where='ring', err=f'{type(e).__name__}: {e}')
        try:
            # 11-28: 찾은 테두리 자리로 6번 넘게 못 찾으면 기본 자리도 번갈아 시험 → 기본 자리에서 찾으면 찾은 테두리를 버림 (테두리 오인식에 묶여 있지 않게)
            alt = bool(loc.geom) and miss >= 6 and miss % 2 == 1
            bx = loc.crop_box(w, h, use_geom=not alt); img = capture.grab((x + bx[0], y + bx[1], x + bx[2], y + bx[3]))
            res = loc.locate(img)
            if res and alt:
                diag.log('ring', drop=[int(v) for v in loc.geom], why='기본 자리에서 찾음'); loc.geom = None
            diag.frame(res, img, loc.info)
        except Exception as e:
            res = None; St.debug = f'화면을 읽지 못했어요: {type(e).__name__}'; diag.once('caperr', 'error', where='capture', err=f'{type(e).__name__}: {e}')
        if res:
            s, mp, u, v = res; St.score = s; miss = 0
            if not t_lock:
                t_lock = time.time()
            St.pos = mp.world(u, v); St.city = int(mp.id); St.since = time.time()
            setstate('lock', f'미니맵으로 위치 찾음 (일치 {s * 100:.0f}%)')
            time.sleep(max(0.0, 0.1 - (time.time() - t0)))                 # 초당 10번까지
        else:
            miss += 1; t_lock = 0.0
            if miss > 3:
                St.pos = None; setstate('search', '미니맵을 찾는 중 — 게임 화면(미니맵)이 보이게 해 주세요')
            time.sleep(0.25 if miss < 20 else 0.8)                         # 못 찾는 동안은 천천히 (CPU 아낌)


# ---------- 웹소켓 서버 (표준 라이브러리 · 기존 트래커와 같은 메시지) ----------
GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def frame(text):
    b = text.encode(); n = len(b)
    hdr = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x81, 127]) + struct.pack('>Q', n)
    return hdr + b


async def read_frame(r):
    h = await r.readexactly(2); op = h[0] & 0x0F; n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack('>H', await r.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack('>Q', await r.readexactly(8))[0]
    mask = await r.readexactly(4) if h[1] & 0x80 else b'\0\0\0\0'
    data = bytearray(await r.readexactly(n))
    for i in range(n):
        data[i] ^= mask[i % 4]
    return op, bytes(data)


async def client(r, w):
    counted = False
    try:
        req = (await r.readuntil(b'\r\n\r\n')).decode('latin-1')
        hdr = {k.strip().lower(): v.strip() for k, v in (l.split(':', 1) for l in req.split('\r\n')[1:] if ':' in l)}
        if hdr.get('origin') not in ORIGINS or 'sec-websocket-key' not in hdr:
            diag.log('ws', ok=False, origin=hdr.get('origin', '')[:80], reason='허용 안 된 사이트' if hdr.get('origin') not in ORIGINS else '웹소켓 아님')
            w.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n'); await w.drain(); w.close(); return
        acc = base64.b64encode(hashlib.sha1((hdr['sec-websocket-key'] + GUID).encode()).digest()).decode()
        w.write(f'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n'.encode())
        await w.drain(); St.clients += 1; counted = True; diag.log('ws', ok=True, origin=hdr.get('origin'), clients=St.clients)

        async def rx():
            while True:
                op, data = await read_frame(r)
                if op == 8:
                    return
                if op == 1:
                    try:
                        t = json.loads(data).get('t')
                        if t == 'reacquire':
                            St.reacquire.set()
                        elif t == 'gacha_get':                            # 관측 기록 (gacha_ocr.py · 화면 글자 인식으로 모은 것)
                            import gacha_ocr
                            rep = gacha_ocr.on_message(data)
                            if rep:
                                w.write(frame(rep)); await w.drain()
                    except Exception:
                        pass
        task = asyncio.create_task(rx()); last = None
        while not task.done() and not St.quit:
            msg = {'t': 'pos', 'app': 'promilia-tracker', 'v': 1, 'ver': VER, 'state': St.state, 'msg': St.msg, 'src': 'screen', 'gacha': St.gacha_count}
            if St.state == 'lock' and St.pos and time.time() - St.since < 2:
                msg.update(x=round(float(St.pos[0]), 2), y=round(float(St.pos[1]), 2), z=round(float(St.pos[2]), 2))
                if St.city:
                    msg['scene'] = St.city
            s = json.dumps(msg, ensure_ascii=False)
            if s != last:
                w.write(frame(s)); await w.drain(); last = s
            await asyncio.sleep(0.05)
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        pass
    finally:
        if counted:
            St.clients -= 1
        try:
            w.close()
        except Exception:
            pass


def server_thread():
    async def run():
        try:
            srv = await asyncio.start_server(client, '127.0.0.1', PORT)
        except OSError as e:
            St.server = 'error'; St.error = f'웹소켓 포트 {PORT} 를 열 수 없어요 (트래커가 이미 켜져 있는지 확인해 주세요): {e}'; diag.log('server', ok=False, port=PORT, err=str(e)); return
        St.server = 'on'
        async with srv:
            while not St.quit:
                await asyncio.sleep(0.3)
    asyncio.run(run())


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)                     # 화면 좌표를 실제 px 로
    except Exception:
        pass
    load_cfg()
    diag.init(St.cfg, HERE, VER)                                         # 진단 로그 (동의했을 때만 · diag.py)
    threading.Thread(target=server_thread, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    try:                                                             # 관측 기록 모으기 (화면 글자 인식)
        import gacha_ocr
        gacha_ocr.start(St, HERE, game_rect)
    except Exception as e:
        St.debug = f'관측 기록 기능을 켜지 못했어요: {e}'
    if '--nogui' in sys.argv:
        try:
            while True:
                time.sleep(1); print(St.state, St.msg, St.city, [round(float(v), 1) for v in St.pos] if St.pos else None, St.error, flush=True)
        except KeyboardInterrupt:
            St.quit = True
    else:
        import gui, updater
        upd = updater.Updater(St, St.cfg.get('repo') or REPO, VER, APP, prefix=TAG_PREFIX, auto=lambda: St.cfg.get('autoupdate', True))
        upd.start_auto()                                             # 켤 때 + 켜 둔 동안 6시간마다 조용히 확인 (설정에서 끌 수 있음)
        ico = os.path.join(getattr(sys, '_MEIPASS', HERE), 'assets', 'tracker.ico')
        gui.App(St, save_cfg, {'app': APP, 'ver': VER, 'port': PORT, 'map': MAP_URL, 'ico': ico, 'admin': lambda: True, 'diag': diag,
                               'upd': upd, 'repo_url': upd.repo_page(), 'toggles': [('auto', '게임 창 자동 찾기')],
                               'info': f'웹소켓 ws://127.0.0.1:{PORT} · 연결 허용: azprguide.xyz · azur-promilia.pages.dev\n게임 화면의 미니맵만 캡처해요 (메모리 읽기 없음 · 화면은 PC 밖으로 보내지 않음)'}).run()


if __name__ == '__main__':
    main()
