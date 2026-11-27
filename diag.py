"""진단 로그 (2026-11-27) — 사용자가 동의했을 때만, 이 PC(exe 옆 promilia-tracker2-diag.log)에만 적음. 어디로도 자동으로 보내지 않음.
「진단 파일 만들기」를 누르면 로그 + 지금 환경 요약 + (위치를 못 찾을 때의) 미니맵 조각 최근 3장을 ZIP 하나로 바탕화면에 만듦 → 사용자가 직접 문의에 첨부.

수집: 트래커 버전 · Windows 버전 · 모니터 해상도 · 배율 · 개수 · 게임 창 크기 · 비율 · 위치 · 창 모드 · 미니맵 자리 · 점수 · 위치 맞추기 결과 ·
      지도 자료 받기 결과 · 사이트 연결 기록(사이트 주소 · 허용 여부) · 오류
수집 안 함: 전체 화면 · 다른 창 · 게임 UID · 관측 기록 · 글자 인식 내용 · PC 이름 · Windows 사용자 이름(경로는 ~ 로 가림) · IP
거부하면 아무것도 적지 않고, 진단 파일(피드백)도 만들 수 없음. 동의 · 거부는 고급 설정에서 바꿀 수 있음.
"""
import collections, ctypes, ctypes.wintypes as W, io, json, os, platform, threading, time, zipfile

CONSENT_VER = 1                     # 안내 내용이 바뀌면 올림 → 다시 물어봄
MAX_BYTES = 1024 * 1024             # 로그 파일 1MB 넘으면 .1 로 넘기고 새로 (최근 것만 남김)
NOTICE_TITLE = '로그 수집 안내'
NOTICE = [
    ('p', '트래커가 잘 작동하지 않을 때(내 위치를 못 찾는 등) 원인을 찾기 위해, 작동 기록(로그)을 이 PC 에만 저장해요. 자동으로 어디에도 보내지 않아요.'),
    ('p', '문제가 생기면 고급 설정의 「진단 파일 만들기」로 만든 파일을 문의에 직접 첨부해 주세요.'),
    ('h', '수집하는 것'),
    ('li', '트래커 버전 · Windows 버전'),
    ('li', '모니터 해상도 · 배율 · 개수, 게임 창 크기 · 화면 비율 · 창 모드'),
    ('li', '미니맵 위치 찾기 결과(찾은 자리 · 일치 점수) · 지도 자료 받기 결과'),
    ('li', '사이트 연결 기록(연결한 사이트 주소 · 허용 여부) · 오류 내용'),
    ('li', '위치를 못 찾을 때의 미니맵 부분 그림 최근 3장 (진단 파일을 만들 때만 저장)'),
    ('h', '수집하지 않는 것'),
    ('li', '전체 화면 · 다른 창, 게임 UID · 관측 기록, PC 이름 · 사용자 이름 · IP'),
    ('w', '거부해도 트래커는 그대로 쓸 수 있어요. 다만 진단 파일을 만들 수 없어 작동 문제 피드백(문의)은 받을 수 없어요. 고급 설정에서 언제든 바꿀 수 있어요.'),
]

_lock = threading.Lock()
S = {'on': False, 'path': '', 'ver': '', 'here': '', 'crops': collections.deque(maxlen=3), 'last': {}, 'stat': None, 'stat_t': 0.0}


def _mask(s):
    """경로 · 문자열에서 Windows 사용자 폴더 · 사용자 이름 · PC 이름을 가림"""
    s = str(s)
    for v, r in ((os.path.expanduser('~'), '~'), (os.environ.get('USERNAME', ''), '<user>'), (os.environ.get('COMPUTERNAME', ''), '<pc>')):
        if v and len(v) > 1:
            s = s.replace(v, r)
    return s


def consent(cfg):
    """'yes' · 'no' · None(아직 안 물어봄 또는 안내가 바뀜)"""
    return cfg.get('diag') if cfg.get('diag_ver') == CONSENT_VER and cfg.get('diag') in ('yes', 'no') else None


def init(cfg, here, ver):
    S['here'], S['ver'] = here, ver
    S['path'] = os.path.join(here, 'promilia-tracker2-diag.log')
    set_on(consent(cfg) == 'yes')


def set_on(on):
    was = S['on']; S['on'] = bool(on)
    if not on:
        S['crops'].clear()
    if on and not was:
        log('start', ver=S['ver'], **env())


def log(kind, **kw):
    if not S['on']:
        return
    line = time.strftime('%Y-%m-%d %H:%M:%S') + f' {kind} ' + _mask(json.dumps(kw, ensure_ascii=False, default=lambda o: round(float(o), 4) if hasattr(o, '__float__') else str(o)))
    with _lock:
        try:
            if os.path.exists(S['path']) and os.path.getsize(S['path']) > MAX_BYTES:
                os.replace(S['path'], S['path'] + '.1')
            with open(S['path'], 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass


def once(key, kind, **kw):
    """같은 내용이면 다시 적지 않음 (상태가 바뀔 때만)"""
    sig = json.dumps(kw, sort_keys=True, default=str)
    if S['last'].get(key) != sig:
        S['last'][key] = sig; log(kind, **kw)


# ---------- 환경 ----------
def monitors():
    out = []
    try:
        u32 = ctypes.windll.user32; shc = ctypes.windll.shcore

        class MI(ctypes.Structure):
            _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('dwFlags', W.DWORD)]
        CB = ctypes.WINFUNCTYPE(ctypes.c_int, W.HMONITOR, W.HDC, ctypes.POINTER(W.RECT), W.LPARAM)

        def cb(h, dc, rc, lp):
            mi = MI(); mi.cbSize = ctypes.sizeof(MI); u32.GetMonitorInfoW(h, ctypes.byref(mi)); r = mi.rcMonitor
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            try:
                shc.GetDpiForMonitor(h, 0, ctypes.byref(dx), ctypes.byref(dy)); sc = round(dx.value / 96 * 100)
            except Exception:
                sc = None
            out.append({'x': r.left, 'y': r.top, 'w': r.right - r.left, 'h': r.bottom - r.top, 'scale%': sc, 'main': bool(mi.dwFlags & 1)})
            return 1
        u32.EnumDisplayMonitors(None, None, CB(cb), 0)
    except Exception as e:
        out.append({'err': type(e).__name__})
    return out


def env():
    return {'windows': f'{platform.release()} {platform.version()}', 'python': platform.python_version(), 'monitors': monitors()}


def ratio(w, h):
    r = w / h if h else 0
    for name, v in (('16:9', 16 / 9), ('16:10', 1.6), ('21:9', 2.37), ('32:9', 3.56), ('4:3', 4 / 3), ('5:4', 1.25), ('3:2', 1.5)):
        if abs(r - v) / v < 0.03:
            return name
    return f'{r:.3f}:1'


def game(hwnd, rect):
    """게임 창 크기 · 비율 · 창 모드 (상태가 바뀔 때만 기록)"""
    if not S['on']:
        return
    if not rect:
        once('game', 'game', found=False); return
    x, y, w, h = rect; mode = '?'
    try:
        u32 = ctypes.windll.user32; st = u32.GetWindowLongW(hwnd, -16)
        mon = next((m for m in monitors() if m.get('x') is not None and m['x'] <= x < m['x'] + m['w'] and m['y'] <= y < m['y'] + m['h']), None)
        if st & 0x00C00000:
            mode = '창 모드(제목줄 있음)'
        elif mon and w == mon['w'] and h == mon['h']:
            mode = '전체 화면 또는 테두리 없는 창'
        else:
            mode = '테두리 없는 창(모니터보다 작음)'
        mtxt = f"{mon['w']}x{mon['h']} {mon['scale%']}%" if mon else '?'
    except Exception:
        mtxt = '?'
    once('game', 'game', found=True, x=x, y=y, w=w, h=h, ratio=ratio(w, h), mode=mode, monitor=mtxt)


# ---------- 위치 찾기 ----------
def frame(res, patch, info):
    """한 번 위치를 찾을 때마다 — 30초마다 요약 한 줄 · 못 찾는 이유가 바뀌면 바로 · 못 찾을 때 미니맵 조각을 메모리에 최근 3장"""
    if not S['on']:
        return
    now = time.time(); st = S['stat']
    if st is None:
        st = S['stat'] = {'n': 0, 'ok': 0, 'best': 0.0, 'why': collections.Counter(), 't': now}
    st['n'] += 1
    if res:
        st['ok'] += 1; st['best'] = max(st['best'], float(res[0]))
        once('loc', 'locate', ok=True, map=res[1].name)
    else:
        why = (info or {}).get('why', '?'); st['why'][why] += 1
        once('loc', 'locate', ok=False, why=why, **{k: v for k, v in (info or {}).items() if k != 'why'})
        if patch is not None and (not S['crops'] or now - S['crops'][-1][0] > 5):
            S['crops'].append((now, patch.copy()))
    if now - st['t'] >= 30:
        log('stat', frames=st['n'], found=st['ok'], best=round(st['best'], 3), fail=dict(st['why']))
        S['stat'] = None


# ---------- 진단 파일 ----------
def make_zip(St=None, extra=None):
    """바탕화면(없으면 exe 옆)에 진단 ZIP — 만든 파일 경로를 돌려줌. 동의하지 않았으면 None"""
    if not S['on']:
        return None
    desk = os.path.join(os.path.expanduser('~'), 'Desktop')
    out_dir = desk if os.path.isdir(desk) else S['here']
    path = os.path.join(out_dir, time.strftime('PromiliaTracker-진단-%y%m%d-%H%M%S.zip'))
    summary = {'tracker': S['ver'], 'made': time.strftime('%Y-%m-%d %H:%M:%S'), **env()}
    if St is not None:
        summary.update(state=St.state, msg=St.msg, game=St.game, server=St.server, clients=St.clients, error=St.error, debug=St.debug,
                       city=St.city, score=round(float(St.score or 0), 3))
    if extra:
        summary.update(extra)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('요약.json', _mask(json.dumps(summary, ensure_ascii=False, indent=1, default=str)))
        for p in (S['path'] + '.1', S['path']):
            if os.path.exists(p):
                with _lock:
                    z.writestr(os.path.basename(p), _mask(open(p, encoding='utf-8', errors='replace').read()))
        for i, (t, im) in enumerate(list(S['crops'])):
            b = io.BytesIO(); im.save(b, 'PNG'); z.writestr(f'미니맵_{i + 1}_{time.strftime("%H%M%S", time.localtime(t))}.png', b.getvalue())
    log('zip', file=os.path.basename(path))
    return path
