"""프로밀리아 가이드 트래커 화면 (promilia-tracker 의 gui.py 를 가져와 화면 인식 방식에 맞게 고침 · tkinter)

라운디드 스퀘어 카드 · 버튼은 캔버스에 직접 그림 (작은 R · 프로밀리아 가이드 사이트와 같은 금색 · 어두운 배경)
글꼴: Noto Serif KR(사이트와 같은 글꼴 · Windows 11 기본 포함) → 없으면 맑은 고딕
아이콘: 선으로 그린 벡터 아이콘(연결 · 다시 찾기 · 종료 · 지도 · 위치) — 그림 파일 없이 캔버스에 그림
"""
import math, os, sys, time, webbrowser
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
        self.hover = None; self.adv = False; self.btns = {}
        self.cv.bind('<Motion>', self.on_move); self.cv.bind('<Button-1>', self.on_click); self.cv.bind('<Leave>', lambda e: self.set_hover(None))
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

    def draw(self):
        S = self.St; cv, P = self.cv, self.px; cv.delete('all'); self.btns = {}
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
            h = 120
            rrect(cv, P(x1), P(y), P(x2), P(y + h), P(R), fill=C['card'], outline=C['gold2'])
            icon(cv, 'down', P(x1 + 30), P(y + 26), P(18), C['gold'], 'upi')
            cv.create_text(P(x1 + 48), P(y + 26), text=U.get('msg') or '', anchor='w', fill=C['tx'], font=self.font(14, True), width=P(x2 - x1 - 70))
            note = (U.get('notes') or '').split('\n')[0] or f"지금 v{self.meta['ver']} → 새 v{U.get('ver')}"
            cv.create_text(P(x1 + 18), P(y + 52), text=note, anchor='w', fill=C['tx2'], font=self.font(12), width=P(x2 - x1 - 36))
            hw = (x2 - x1 - 36 - 8) * 0.68
            self.button('upd_page', x1 + 18, y + 70, x1 + 18 + hw, y + 104, '다운로드 페이지 열기', 'down', 'gold')
            self.button('upd_later', x1 + 26 + hw, y + 70, x2 - 18, y + 104, '나중에', 'refresh', 'dark')
            y += h + 14        # 위치 카드
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
            cv.create_text(P(x1 + 18), P(y + 56), text=S.gacha_status or '게임에서 관측 → 확률 설명 → 기록 화면을 열고 쪽을 넘기면 모여요', anchor='w', fill=C['tx2'], font=self.font(12), width=P(x2 - x1 - 36))
            self.button('gacha', x1 + 18, y + 72, x2 - 18, y + 110, '나의 관측 결산 열기', 'map', 'dark')
        # 고급 설정
        y += 0 if lite else 138; tag = 'b_adv'
        rrect(cv, P(x1), P(y), P(x2), P(y + 46), P(R), fill=C['card'], outline=C['line'], tags=tag)
        cv.create_text(P(x1 + 18), P(y + 23), text='고급 설정', anchor='w', fill=C['tx'], font=self.font(14, True), tags=tag)
        cv.create_text(P(x2 - 20), P(y + 23), text='▴' if self.adv else '▾', fill=C['tx2'], font=self.font(14), tags=tag)
        self.btns['adv'] = (x1, y, x2, y + 46); y += 46
        if self.adv:
            y += 10; h = 296
            rrect(cv, P(x1), P(y), P(x2), P(y + h), P(R), fill=C['card'], outline=C['line'])
            err = S.error or ('' if self.meta['admin']() else '')
            rrect(cv, P(x1 + 18), P(y + 16), P(x2 - 18), P(y + 66), P(RB), fill=C['card2'], outline='')
            cv.create_text(P(x1 + 32), P(y + 41), text=err or '현재 보고된 트래커 오류 없음', anchor='w', fill=C['red'] if err else C['tx2'], font=self.font(12), width=P(x2 - x1 - 64))
            self.toggle('auto', x1 + 18, y + 84, '게임 창 자동 찾기', S.cfg.get('auto', True))
            if self.meta.get('upd'):
                self.toggle('autoupdate', x1 + 18, y + 152, '켤 때 새 버전 확인 (GitHub 릴리스)', S.cfg.get('autoupdate', True))
            up = self.meta.get('upd')
            if up:
                um = U.get('msg') or (f"지금 버전 v{self.meta['ver']}" if up.repo else '업데이트 저장소가 정해지지 않았어요')
                cv.create_text(P(x1 + 18), P(y + 202), text=um, anchor='w', fill=C['red'] if U.get('state') == 'error' else C['tx2'], font=self.font(12), width=P(x2 - x1 - 190))
                self.button('upd_chk', x2 - 18 - 150, y + 186, x2 - 18, y + 218, '업데이트 확인', 'refresh', 'dark')
            info = f"웹소켓 ws://127.0.0.1:{self.meta['port']} · 연결 허용: azur-promilia.pages.dev\n게임 화면의 미니맵만 캡처해요 (메모리 읽기 없음 · 화면은 PC 밖으로 보내지 않음)"
            if S.debug:
                info += '\n' + S.debug
            cv.create_text(P(x1 + 18), P(y + 238), text=info, anchor='nw', fill=C['tx3'], font=self.font(11), width=P(x2 - x1 - 36))
            y += h
        y += 18
        if int(cv.cget('height')) != P(y):
            cv.configure(height=P(y))

    # ---------- 입력 ----------
    def hit(self, e):
        x, y = e.x / self.k, e.y / self.k
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
               U.get('state'), U.get('msg'), U.get('hide'))
        if sig != self.sig:
            self.sig = sig; self.draw()
        self.root.after(100, self.tick)

    def run(self):
        self.root.mainloop()
