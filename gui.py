"""프로밀리아 가이드 트래커 화면 — 두 트래커 공용 (promilia-tracker2 화면 인식 · promilia-tracker 메모리에 같은 파일 · tkinter)
트래커마다 다른 것은 meta 로 받음: app · ver · port · map · ico · admin(권한 확인) · admin_msg · diag(diag 모듈) · upd(updater.Updater)
  · repo_url(GitHub 버튼) · toggles([(설정 키, 이름)]) · info(고급 설정 아래 안내 글) · gacha_hint(관측 기록 카드 안내) · lite(관측 기록 카드 숨김)

라운디드 스퀘어 카드 · 버튼은 캔버스에 직접 그림 (작은 R · 프로밀리아 가이드 사이트와 같은 금색 · 어두운 배경)
글꼴: Noto Serif KR(사이트와 같은 글꼴 · Windows 11 기본 포함) → 없으면 맑은 고딕
아이콘: 선으로 그린 벡터 아이콘(연결 · 다시 찾기 · 종료 · 지도 · 위치) — 그림 파일 없이 캔버스에 그림
"""
import math, os, subprocess, sys, time, webbrowser
import tkinter as tk
import tkinter.font as tkfont

C = dict(bg='#0b0b0d', card='#131317', card2='#1a1a20', line='#2a2a31', tx='#f1eee6', tx2='#a29f97', tx3='#6f6c66',
         gold='#d9b56a', gold2='#b98a3a', gold_tx='#1b1406', red_bg='#2b1214', red='#ff6b6b', grn_bg='#0f2519', grn='#3fd47f',
         warn_bg='#2b2310', warn='#f2c463', btn='#ece8de', btn_tx='#141414', btn_h='#ffffff', danger='#8c2323', danger_h='#a32b2b')
SCENES = {100: '새싹 골짜기', 101: '플리스 성방', 200: '샤루루 마을', 701: '하우징'}
W = 470          # 창 너비(논리 px) — 높이는 내용에 맞춤
R = 10           # 카드 모서리
RB = 8           # 버튼 · 칩 모서리


def rrect(cv, x1, y1, x2, y2, r, **kw):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


def icon(cv, kind, cx, cy, s, col, tag):
    """s = 아이콘 한 변(px) · 선 아이콘"""
    w = max(1.6, s / 9); h = s / 2; kw = dict(fill=col, width=w, capstyle='round', joinstyle='round', tags=tag)
    if kind == 'plug':                        # 연결
        cv.create_line(cx - h * .9, cy + h * .9, cx - h * .35, cy + h * .35, **kw)
        cv.create_line(cx + h * .35, cy - h * .35, cx + h * .9, cy - h * .9, **kw)
        cv.create_oval(cx - h * .5, cy - h * .5, cx + h * .5, cy + h * .5, outline=col, width=w, tags=tag)
        cv.create_line(cx - h * .1, cy - h * .75, cx + h * .75, cy + h * .1, **kw)
    elif kind == 'refresh':                   # 다시 찾기
        cv.create_arc(cx - h * .8, cy - h * .8, cx + h * .8, cy + h * .8, start=40, extent=290, style='arc', outline=col, width=w, tags=tag)
        a = math.radians(40); ex, ey = cx + h * .8 * math.cos(a), cy - h * .8 * math.sin(a)
        cv.create_line(ex - h * .45, ey - h * .05, ex, ey, ex + h * .05, ey - h * .45, **kw)
    elif kind == 'power':                     # 종료
        cv.create_arc(cx - h * .8, cy - h * .7, cx + h * .8, cy + h * .9, start=120, extent=300, style='arc', outline=col, width=w, tags=tag)
        cv.create_line(cx, cy - h * .95, cx, cy + h * .05, **kw)
    elif kind == 'map':                       # 지도
        cv.create_line(cx - h * .9, cy - h * .6, cx - h * .3, cy - h * .85, cx + h * .3, cy - h * .6, cx + h * .9, cy - h * .85, cx + h * .9, cy + h * .6,
                       cx + h * .3, cy + h * .85, cx - h * .3, cy + h * .6, cx - h * .9, cy + h * .85, cx - h * .9, cy - h * .6, **kw)
        cv.create_line(cx - h * .3, cy - h * .85, cx - h * .3, cy + h * .6, **kw); cv.create_line(cx + h * .3, cy - h * .6, cx + h * .3, cy + h * .85, **kw)
    elif kind == 'gps':                       # 위치
        cv.create_oval(cx - h * .75, cy - h * .75, cx + h * .75, cy + h * .75, outline=col, width=w, tags=tag)
        cv.create_oval(cx - h * .28, cy - h * .28, cx + h * .28, cy + h * .28, fill=col, outline='', tags=tag)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            cv.create_line(cx + dx * h * .75, cy + dy * h * .75, cx + dx * h, cy + dy * h, **kw)
    elif kind == 'down':                      # 업데이트 (아래 화살표 + 받침)
        cv.create_line(cx, cy - h * .85, cx, cy + h * .35, **kw)
        cv.create_line(cx - h * .5, cy - h * .1, cx, cy + h * .4, cx + h * .5, cy - h * .1, **kw)
        cv.create_line(cx - h * .85, cy + h * .85, cx + h * .85, cy + h * .85, **kw)
    elif kind == 'gh':                        # GitHub 저장소 (갈래 아이콘: 점 3개 + 줄기)
        r_ = h * .24
        for px_, py_ in ((-h * .45, -h * .65), (-h * .45, h * .65), (h * .5, -h * .3)):
            cv.create_oval(cx + px_ - r_, cy + py_ - r_, cx + px_ + r_, cy + py_ + r_, outline=col, width=w, tags=tag)
        cv.create_line(cx - h * .45, cy - h * .41, cx - h * .45, cy + h * .41, **kw)
        cv.create_line(cx + h * .5, cy - h * .06, cx + h * .5, cy + h * .05, cx - h * .2, cy + h * .4, **kw)
    elif kind == 'star':                      # 로고 ✦
        k = h; pts = []
        for i in range(8):
            a = math.pi / 2 + i * math.pi / 4; rr = k if i % 2 == 0 else k * .26
            pts += [cx + rr * math.cos(a), cy - rr * math.sin(a)]
        cv.create_polygon(pts, fill=col, outline='', tags=tag)


class App:
    def __init__(self, St, cfg_save, meta):
        self.St, self.save, self.meta = St, cfg_save, meta
        try:
            ctypes = __import__('ctypes'); ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = tk.Tk(); self.root.title(meta['app']); self.root.configure(bg=C['bg']); self.root.resizable(False, False)
        self.k = max(1.0, self.root.winfo_fpixels('1i') / 96)           # 화면 배율
        fams = set(tkfont.families(self.root))
        self.ff = 'Noto Serif KR' if 'Noto Serif KR' in fams else 'Malgun Gothic'
        self.fb = 'Noto Serif KR SemiBold' if 'Noto Serif KR SemiBold' in fams else self.ff
        try:
            self.root.iconbitmap(default=meta.get('ico', ''))
        except Exception:
            pass
        self.cv = tk.Canvas(self.root, width=self.px(W), height=self.px(600), bg=C['bg'], highlightthickness=0); self.cv.pack()
        self.hover = None; self.adv = False; self.btns = {}; self.note = ''
        self.cv.bind('<Motion>', self.on_move); self.cv.bind('<Button-1>', self.on_click); self.cv.bind('<Leave>', lambda e: self.set_hover(None))
        # 창이 화면보다 길어지면(새 버전 카드 + 고급 설정을 펼친 경우 등 · 1080p 화면) 화면 높이에 맞추고 마우스 휠로 내려 봄 (11-27)
        self.cv.configure(yscrollincrement=self.px(40))
        self.cv.bind('<MouseWheel>', lambda e: self.cv.yview_scroll(int(-e.delta / 120), 'units') if self.cv.bbox('all') and self.full_h > int(self.cv.cget('height')) else None)
        self.full_h = 0
        self.root.protocol('WM_DELETE_WINDOW', self.quit)
        self.sig = None; self.tick()

    def px(self, v):
        return int(round(v * self.k))

    def font(self, size, bold=False, mono=False):
        return ('Consolas' if mono else (self.fb if bold else self.ff), -self.px(size), 'bold' if bold and (mono or self.fb == self.ff) else 'normal')

    # ---------- 그리기 ----------
    def button(self, key, x1, y1, x2, y2, text, ico, kind='light'):
        cv, P = self.cv, self.px; hov = self.hover == key
        fill, tx = {'light': (C['btn_h'] if hov else C['btn'], C['btn_tx']), 'dark': (C['line'] if hov else C['card2'], C['tx']),
                    'danger': (C['danger_h'] if hov else C['danger'], '#fff'), 'gold': ('#e6c27a' if hov else C['gold'], C['gold_tx'])}[kind]
        tag = 'b_' + key
        rrect(cv, P(x1), P(y1), P(x2), P(y2), P(RB), fill=fill, outline='', tags=tag)
        f = self.font(14, True); tw = tkfont.Font(root=self.root, font=f).measure(text); isz = P(17); gap = P(8)
        cx = (P(x1) + P(x2)) / 2 - (isz + gap + tw) / 2
        icon(cv, ico, cx + isz / 2, (P(y1) + P(y2)) / 2, isz, tx, tag)
        cv.create_text(cx + isz + gap, (P(y1) + P(y2)) / 2, text=text, anchor='w', fill=tx, font=f, tags=tag)
        self.btns[key] = (x1, y1, x2, y2)

    def chip(self, x1, y1, x2, y2, text, bg, fg):
        cv, P = self.cv, self.px
        rrect(cv, P(x1), P(y1), P(x2), P(y2), P(RB), fill=bg, outline='')
        cv.create_oval(P(x1 + 14), P((y1 + y2) / 2 - 4), P(x1 + 22), P((y1 + y2) / 2 + 4), fill=fg, outline='')
        cv.create_text(P(x1 + 32), P((y1 + y2) / 2), text=text, anchor='w', fill=fg, font=self.font(14, True))

    def toggle(self, key, x, y, text, on):
        cv, P = self.cv, self.px; tag = 'b_' + key
        # 토글 (11-26 다시): 바깥 틀과 손잡이 모두 라운디드 스퀘어(작은 R) — 카드 · 버튼과 같은 모양
        rrect(cv, P(x), P(y), P(x + 40), P(y + 22), P(6), fill=C['gold'] if on else C['line'], outline='', tags=tag)
        kx = x + (21 if on else 3)
        rrect(cv, P(kx), P(y + 3), P(kx + 16), P(y + 19), P(4), fill='#fff' if on else C['tx2'], outline='', tags=tag)
        cv.create_text(P(x + 48), P(y + 11), text=text, anchor='w', fill=C['tx'], font=self.font(13), tags=tag)
        self.btns[key] = (x, y - 2, W - 40, y + 24)

    def dg(self):
        return self.meta.get('diag')

    def consent_pending(self):
        d = self.dg(); return bool(d) and d.consent(self.St.cfg) is None

    def set_consent(self, yes):
        """로그 수집 동의 · 거부 (처음 실행 화면 · 고급 설정) — 거부하면 지금까지 모은 로그도 지움"""
        d = self.dg(); S = self.St
        S.cfg['diag'] = 'yes' if yes else 'no'; S.cfg['diag_ver'] = d.CONSENT_VER; self.save()
        if not yes:
            d.set_on(False)
            for p in (d.S['path'], d.S['path'] + '.1'):
                try:
                    os.remove(p)
                except OSError:
                    pass
        else:
            d.set_on(True)

    def draw_consent(self):
        """처음 실행할 때 로그 수집 동의 화면 (diag.NOTICE) — 동의 · 거부 어느 쪽이든 트래커는 시작함"""
        d = self.dg(); cv, P = self.cv, self.px; x1, x2 = 20, W - 20; y = 18; top = y
        rid = rrect(cv, P(x1), P(y), P(x2), P(y + 10), P(R), fill=C['card'], outline=C['line'])
        icon(cv, 'star', P(x1 + 30), P(y + 32), P(22), C['gold'], 'logo')
        cv.create_text(P(x1 + 50), P(y + 32), text=d.NOTICE_TITLE, anchor='w', fill=C['tx'], font=self.font(18, True))
        y += 58; wrap = P(x2 - x1 - 40)
        for kind, text in d.NOTICE:
            if kind == 'h':
                y += 6; t = cv.create_text(P(x1 + 20), P(y), text=text, anchor='nw', fill=C['gold'], font=self.font(13, True), width=wrap)
            elif kind == 'li':
                cv.create_text(P(x1 + 24), P(y), text='·', anchor='nw', fill=C['tx2'], font=self.font(13, True))
                t = cv.create_text(P(x1 + 36), P(y), text=text, anchor='nw', fill=C['tx'], font=self.font(12), width=P(x2 - x1 - 56))
            elif kind == 'w':
                y += 6; t = cv.create_text(P(x1 + 20), P(y), text=text, anchor='nw', fill=C['warn'], font=self.font(12), width=wrap)
            else:
                t = cv.create_text(P(x1 + 20), P(y), text=text, anchor='nw', fill=C['tx2'], font=self.font(12), width=wrap)
            y = cv.bbox(t)[3] / self.k + (4 if kind == 'li' else 8)
        y += 8; bw = (x2 - x1 - 40 - 10) / 2
        self.button('dg_yes', x1 + 20, y, x1 + 20 + bw, y + 42, '동의하고 시작', 'gps', 'gold')
        self.button('dg_no', x1 + 30 + bw, y, x2 - 20, y + 42, '거부하고 시작', 'power', 'dark')
        y += 60
        cv.delete(rid); rid = rrect(cv, P(x1), P(top), P(x2), P(y), P(R), fill=C['card'], outline=C['line']); cv.tag_lower(rid)
        y += 18
        self.fit(y)

    def fit(self, y):
        """창 높이 = 내용 높이 (화면보다 길면 화면 높이까지 · 나머지는 마우스 휠로)"""
        full = self.px(y); self.full_h = full
        h = min(full, self.root.winfo_screenheight() - self.px(90))
        self.cv.configure(scrollregion=(0, 0, self.px(W), full))
        if int(self.cv.cget('height')) != h:
            self.cv.configure(height=h)
        if full <= h:
            self.cv.yview_moveto(0)

    def draw(self):
        S = self.St; cv, P = self.cv, self.px; cv.delete('all'); self.btns = {}
        if self.consent_pending():
            return self.draw_consent()
        x1, x2 = 20, W - 20; y = 18
        # 머리 카드
        rrect(cv, P(x1), P(y), P(x2), P(y + 182), P(R), fill=C['card'], outline=C['line'])
        icon(cv, 'star', P(x1 + 30), P(y + 34), P(24), C['gold'], 'logo')
        cv.create_text(P(x1 + 50), P(y + 34), text=self.meta['app'], anchor='w', fill=C['tx'], font=self.font(19, True))
        vt = f"v{self.meta['ver']}"; vw = tkfont.Font(root=self.root, font=self.font(12, True)).measure(vt) / self.k + 18
        rrect(cv, P(x2 - 18 - vw), P(y + 22), P(x2 - 18), P(y + 46), P(RB), fill='', outline=C['line'])
        cv.create_text(P(x2 - 18 - vw / 2), P(y + 34), text=vt, fill=C['tx'], font=self.font(12, True))
        cv.create_line(P(x1 + 18), P(y + 62), P(x2 - 18), P(y + 62), fill=C['line'])
        g = {'on': ('게임 창 찾음', C['grn_bg'], C['grn']), 'denied': ('권한 없음', C['warn_bg'], C['warn'])}.get(S.game, ('게임 창 없음', C['red_bg'], C['red']))
        s = {'on': ('서버 활성', C['grn_bg'], C['grn']), 'error': ('서버 오류', C['red_bg'], C['red'])}.get(S.server, ('서버 시작 중', C['warn_bg'], C['warn']))
        mid = (x1 + x2) / 2
        self.chip(x1 + 18, y + 76, mid - 5, y + 116, g[0], g[1], g[2]); self.chip(mid + 5, y + 76, x2 - 18, y + 116, s[0], s[1], s[2])
        bw = (x2 - x1 - 36 - 16) / 3; by = y + 128
        self.button('connect', x1 + 18, by, x1 + 18 + bw, by + 40, '다시 연결', 'plug')
        self.button('reacq', x1 + 26 + bw, by, x1 + 26 + 2 * bw, by + 40, '다시 찾기', 'refresh')
        self.button('quit', x1 + 34 + 2 * bw, by, x2 - 18, by + 40, '종료', 'power', 'danger')
        y += 196
        # 새 버전 안내 카드 (updater.py) — 새 버전이 있을 때만 · 업데이트는 사용자가 릴리스 페이지에서 직접 받음(강제 업데이트 없음) · 「나중에」로 이번 실행 동안 숨김
        U = getattr(S, 'upd', None) or {}; up = self.meta.get('upd')
        if up and U.get('state') == 'avail' and not U.get('hide'):
            top = y                                       # 카드 높이는 요약 글 줄 수에 맞춤 (11-27 · 두 줄이면 버튼과 겹쳤음)
            rid = rrect(cv, P(x1), P(y), P(x2), P(y + 10), P(R), fill=C['card'], outline=C['gold2'])
            icon(cv, 'down', P(x1 + 30), P(y + 26), P(18), C['gold'], 'upi')
            cv.create_text(P(x1 + 48), P(y + 26), text=U.get('msg') or '', anchor='w', fill=C['tx'], font=self.font(14, True), width=P(x2 - x1 - 70))
            note = (U.get('notes') or '').split('\n')[0] or f"지금 v{self.meta['ver']} → 새 v{U.get('ver')}"
            note = note if len(note) <= 90 else note[:88].rstrip() + '…'
            t = cv.create_text(P(x1 + 18), P(y + 44), text=note, anchor='nw', fill=C['tx2'], font=self.font(12), width=P(x2 - x1 - 36))
            by = cv.bbox(t)[3] / self.k + 10
            hw = (x2 - x1 - 36 - 8) * 0.68
            self.button('upd_page', x1 + 18, by, x1 + 18 + hw, by + 34, '다운로드 페이지 열기', 'down', 'gold')
            self.button('upd_later', x1 + 26 + hw, by, x2 - 18, by + 34, '나중에', 'refresh', 'dark')
            y = by + 34 + 16
            cv.delete(rid); rid = rrect(cv, P(x1), P(top), P(x2), P(y), P(R), fill=C['card'], outline=C['gold2']); cv.tag_lower(rid)
            y += 14            # 위치 카드
        rrect(cv, P(x1), P(y), P(x2), P(y + 214), P(R), fill=C['card'], outline=C['line'])
        live = S.state == 'lock' and S.pos and time.time() - S.since < 2
        icon(cv, 'gps', P(x1 + 30), P(y + 28), P(18), C['gold'] if live else C['tx3'], 'gps')
        scene = (getattr(S, 'scenes', {}).get(str(S.city)) or SCENES.get(S.city, f'장면 {S.city}' if S.city else '지역 확인 중')) if live else '위치'
        cv.create_text(P(x1 + 48), P(y + 28), text=scene, anchor='w', fill=C['tx'], font=self.font(16, True))
        cv.create_text(P(x2 - 18), P(y + 28), text=S.msg, anchor='e', fill=C['grn'] if S.state == 'lock' else C['tx2'], font=self.font(12), width=P(250))
        tw = (x2 - x1 - 36 - 16) / 3
        for i, k in enumerate('XYZ'):
            tx1 = x1 + 18 + i * (tw + 8)
            rrect(cv, P(tx1), P(y + 50), P(tx1 + tw), P(y + 112), P(RB), fill=C['card2'], outline='')
            cv.create_text(P(tx1 + 14), P(y + 66), text=k, anchor='w', fill=C['gold'], font=self.font(12, True))
            cv.create_text(P(tx1 + 14), P(y + 92), text=f'{S.pos[i]:.2f}' if live else '—', anchor='w', fill=C['tx'], font=self.font(19, True, True))
        cl = f'지도 연결 {S.clients}개' if S.clients else '지도 연결 없음 — 사이트 지도에서 「내 위치」를 누르세요'
        cv.create_text(P(x1 + 18), P(y + 132), text=cl, anchor='w', fill=C['tx2'], font=self.font(12))
        self.button('map', x1 + 18, y + 152, x2 - 18, y + 194, '프로밀리아 가이드 지도 열기', 'map', 'gold')
        y += 228
        lite = self.meta.get('lite')                     # 트래커 2: 관측 기록 기능 없음 — 카드를 그리지 않음
        if not lite:
            rrect(cv, P(x1), P(y), P(x2), P(y + 124), P(R), fill=C['card'], outline=C['line'])
            icon(cv, 'star', P(x1 + 30), P(y + 28), P(18), C['gold'] if S.gacha_count else C['tx3'], 'gstar')
            cv.create_text(P(x1 + 48), P(y + 28), text=f'관측 기록 {S.gacha_count:,}건', anchor='w', fill=C['tx'], font=self.font(16, True))
            cv.create_text(P(x1 + 18), P(y + 56), text=S.gacha_status or self.meta.get('gacha_hint') or '게임에서 관측 → 확률 설명 → 기록 화면을 열고 쪽을 넘기면 모여요', anchor='w', fill=C['tx2'], font=self.font(12), width=P(x2 - x1 - 36))
            self.button('gacha', x1 + 18, y + 72, x2 - 18, y + 110, '나의 관측 결산 열기', 'map', 'dark')
        y += 0 if lite else 138
        # GitHub 저장소 (11-27): 새 버전 · 사용 방법 · 소스 — 고급 설정 바로 위
        if self.meta.get('repo_url'):
            self.button('gh', x1, y, x2, y + 44, 'GitHub 열기 (새 버전 · 사용 방법)', 'gh', 'dark')
            y += 56
        # 고급 설정
        tag = 'b_adv'
        rrect(cv, P(x1), P(y), P(x2), P(y + 46), P(R), fill=C['card'], outline=C['line'], tags=tag)
        cv.create_text(P(x1 + 18), P(y + 23), text='고급 설정', anchor='w', fill=C['tx'], font=self.font(14, True), tags=tag)
        cv.create_text(P(x2 - 20), P(y + 23), text='▴' if self.adv else '▾', fill=C['tx2'], font=self.font(14), tags=tag)
        self.btns['adv'] = (x1, y, x2, y + 46); y += 46
        if self.adv:
            # 11-27: 항목을 위에서부터 차례로 쌓음 (예전엔 자리를 숫자로 박아 두어 업데이트 · 로그 항목이 함께 있으면 겹쳤음) — 카드는 다 그린 뒤 높이에 맞춰 뒤에 깖
            y += 10; top = y; y += 16
            rid = rrect(cv, P(x1), P(top), P(x2), P(top + 10), P(R), fill=C['card'], outline=C['line'])
            adm = self.meta.get('admin')
            err = S.error or ('' if (not adm or adm()) else self.meta.get('admin_msg', ''))
            rrect(cv, P(x1 + 18), P(y), P(x2 - 18), P(y + 50), P(RB), fill=C['card2'], outline='')
            cv.create_text(P(x1 + 32), P(y + 25), text=err or '현재 보고된 트래커 오류 없음', anchor='w', fill=C['red'] if err else C['tx2'], font=self.font(12), width=P(x2 - x1 - 64))
            y += 66
            for key, label in self.meta.get('toggles') or [('auto', '게임 창 자동 찾기')]:
                self.toggle(key, x1 + 18, y, label, S.cfg.get(key, True)); y += 34
            up = self.meta.get('upd')
            if up:                                        # 새 버전 확인
                self.toggle('autoupdate', x1 + 18, y, '켤 때 · 켜 둔 동안 새 버전 확인 (GitHub 릴리스)', S.cfg.get('autoupdate', True)); y += 34
                um = U.get('msg') or (f"지금 버전 v{self.meta['ver']}" if up.repo else '업데이트 저장소가 정해지지 않았어요')
                cv.create_text(P(x1 + 18), P(y + 16), text=um, anchor='w', fill=C['red'] if U.get('state') == 'error' else C['tx2'], font=self.font(12), width=P(x2 - x1 - 190))
                self.button('upd_chk', x2 - 18 - 150, y, x2 - 18, y + 32, '업데이트 확인', 'refresh', 'dark'); y += 46
            d = self.dg()
            if d:                                         # 로그 수집 · 진단 파일 (피드백) — 동의했을 때만 만들 수 있음
                agreed = d.consent(S.cfg) == 'yes'
                self.toggle('diag', x1 + 18, y, '로그 수집 동의 (작동 문제 진단용 · 이 PC 에만 저장)', agreed); y += 34
                if agreed:
                    self.button('dg_zip', x1 + 18, y, x2 - 18, y + 36, '진단 파일 만들기 (문의에 첨부)', 'down', 'dark')
                else:
                    rrect(cv, P(x1 + 18), P(y), P(x2 - 18), P(y + 36), P(RB), fill=C['card2'], outline='')
                    cv.create_text(P((x1 + x2) / 2), P(y + 18), text='진단 파일 만들기 — 로그 수집에 동의해야 쓸 수 있어요', fill=C['tx3'], font=self.font(12, True))
                y += 44
                note = self.note or ('작동 문제 피드백(문의)은 진단 파일이 있어야 받을 수 있어요.' if not agreed else '')
                if note:
                    t = cv.create_text(P(x1 + 18), P(y), text=note, anchor='nw', fill=C['warn'] if not agreed else C['tx2'], font=self.font(11), width=P(x2 - x1 - 36))
                    y = cv.bbox(t)[3] / self.k + 8
            info = self.meta.get('info') or ''
            if S.debug:
                info += ('\n' if info else '') + S.debug
            if info:
                y += 4; t = cv.create_text(P(x1 + 18), P(y), text=info, anchor='nw', fill=C['tx3'], font=self.font(11), width=P(x2 - x1 - 36))
                y = cv.bbox(t)[3] / self.k
            y += 16
            cv.delete(rid); rid = rrect(cv, P(x1), P(top), P(x2), P(y), P(R), fill=C['card'], outline=C['line']); cv.tag_lower(rid)
        y += 18
        self.fit(y)

    # ---------- 입력 ----------
    def hit(self, e):
        x, y = self.cv.canvasx(e.x) / self.k, self.cv.canvasy(e.y) / self.k   # 스크롤한 만큼 더함
        return next((k for k, (a, b, c, d) in self.btns.items() if a <= x <= c and b <= y <= d), None)

    def set_hover(self, k):
        if k != self.hover:
            self.hover = k; self.cv.configure(cursor='hand2' if k else ''); self.draw()

    def on_move(self, e):
        self.set_hover(self.hit(e))

    def on_click(self, e):
        k = self.hit(e); S = self.St
        if k == 'connect':
            S.reconnect.set()
        elif k == 'reacq':
            S.reacquire.set()
        elif k == 'quit':
            self.quit()
        elif k == 'map':
            webbrowser.open(self.meta['map'])
        elif k == 'gacha':
            webbrowser.open(self.meta['map'].rsplit('/', 1)[0] + '/gacha-record')
        elif k == 'gh' and self.meta.get('repo_url'):
            webbrowser.open(self.meta['repo_url'])
        elif k == 'adv':
            self.adv = not self.adv
        elif k in ('auto', 'motion', 'autoupdate'):
            S.cfg[k] = not S.cfg.get(k, True); self.save()
        elif k == 'upd_chk' and self.meta.get('upd'):
            self.meta['upd'].check()
        elif k == 'upd_page' and self.meta.get('upd'):
            u = self.meta['upd'].page()
            if u:
                webbrowser.open(u)
        elif k == 'upd_later':
            S.upd['hide'] = True
        elif k in ('dg_yes', 'dg_no'):
            self.set_consent(k == 'dg_yes')
        elif k == 'diag':
            self.set_consent(self.dg().consent(S.cfg) != 'yes'); self.note = ''
        elif k == 'dg_zip':
            try:
                p = self.dg().make_zip(S)
                self.note = f'바탕화면에 만들었어요: {os.path.basename(p)} — 문의하기에 첨부해 주세요' if p else '로그 수집에 동의해야 만들 수 있어요'
                if p:
                    subprocess.Popen(['explorer', '/select,', p])
            except Exception as e:
                self.note = f'진단 파일을 만들지 못했어요: {type(e).__name__}'
        self.draw()

    def quit(self):
        if getattr(self, 'closing', False):
            return
        self.closing = True; self.St.quit = True; self.root.after(150, self.root.destroy)

    def tick(self):
        if self.St.quit:
            return
        S = self.St; live = S.state == 'lock' and S.pos and time.time() - S.since < 2
        U = getattr(S, 'upd', None) or {}
        sig = (S.game, S.server, S.state, S.msg, S.clients, S.error, S.city, S.debug, S.gacha_count, S.gacha_status, tuple(round(v, 2) for v in S.pos) if live else None, self.hover, self.adv,
               U.get('state'), U.get('msg'), U.get('hide'), S.cfg.get('diag'), S.cfg.get('diag_ver'), self.note)
        if sig != self.sig:
            self.sig = sig; self.draw()
        # 새 버전이 처음 확인되면 작업 표시줄 아이콘을 깜빡여 알림 (창을 내려 둔 경우 · 11-27)
        if U.get('state') == 'avail' and U.get('ver') and U.get('ver') != getattr(self, 'flashed', None):
            self.flashed = U.get('ver')
            try:
                hwnd = __import__('ctypes').windll.user32.GetParent(self.root.winfo_id())
                __import__('ctypes').windll.user32.FlashWindow(hwnd, True)
            except Exception:
                pass
        self.root.after(100, self.tick)

    def run(self):
        self.root.mainloop()
