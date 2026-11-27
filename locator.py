"""화면의 미니맵 → 지도 위 위치 (메모리를 읽지 않음)

게임 화면 왼쪽 위의 둥근 미니맵을 잘라, 프로밀리아 가이드의 지도 그림(/img/g/map/<지도>/base.webp)에서 같은 곳을 찾는다.
- 비교: 마스크를 씌운 정규화 상관(밝기 + 색 차이 2개) — numpy FFT 로 계산 (OpenCV 없이)
- 처음 · 놓쳤을 때: 지도 전체에서 찾음(지도마다 1024px 로 줄인 그림) → 붙은 뒤: 직전 위치 둘레만 2048px 그림에서 찾음(빠르고 정밀)
- 미니맵은 반투명이고 가운데에 캐릭터 표시가 있어, 고리 모양(안쪽 30% ~ 바깥 92%)만 비교
- 좌표: 지도 그림 위치(u, v) → 월드 좌표 = 사이트 map.html toUV 의 역변환 (data.json maps[].xf = [ox, oz, 가로, 세로, 회전])
- 높이(y): 3D 보기용 지형 높이 그림(h.webp · 16비트)에서 읽음 (없으면 0)
"""
import io, json, math, os, time, urllib.request
import numpy as np
from PIL import Image, ImageFilter

SITE = 'https://azur-promilia.pages.dev'
BASE = SITE + '/img/g/map/'
# 미니맵 자리 · 크기 (세로 2160 화면 기준 px — 화면 세로에 비례): 가운데 (285, 245) · 비교에 쓰는 반지름 150
MM_CX, MM_CY, MM_R = 285, 245, 150
# 미니맵 축척: 게임 미니맵은 지도 그림(world_area.mapSize · data.json maps[].tex)의 화소 기준으로 확대됨 → 지도마다 1m 당 화면 px 가 다름
#   세로 2160 화면에서 1m = MM_TEX_K × tex(그림 가로 화소) / 지도 가로(m)
#   MM_TEX_K = 새싹 골짜기에서 잰 3.45px/m × 2100m / 8192px (11-26 샤루루 마을에서 확인: 2048px · 350m → 5.18px/m)
MM_PX_PER_M = 3.45                       # 예전 값(tex 가 없는 지도 자료일 때만 씀)
MM_TEX_K = 3.45 * 2100 / 8192
COARSE, FINE = 1024, 2048
# 미니맵 둥근 테두리 (세로 2160 · 16:9 화면에서 잰 값): 가운데 (290, 246) · 반지름 184 — 화면 비율(21:9 · 32:9 · 16:10)이나 UI 배치가 달라도
# 이 테두리를 화면에서 직접 찾아 미니맵 자리를 잡음(find_ring). 못 찾으면 예전처럼 '세로 비례 + 왼쪽 위' 자리
RING_CX, RING_CY, RING_R = 290, 246, 184


def ring_score(a, R, angles=72):
    """회색조 그림 a 의 모든 화소를 가운데로 봤을 때, 반지름 R 원 위 밝기 − 안팎(±5px) 밝기 (밝은 얇은 테두리일수록 큼)"""
    H, W = a.shape; P = R + 8; A = np.pad(a, P, mode='edge'); on = np.zeros((H, W), np.float32); off = np.zeros((H, W), np.float32)
    for t in np.linspace(0, 2 * np.pi, angles, endpoint=False):
        c, s = math.cos(t), math.sin(t)
        for rr, acc, wgt in ((R, on, 1.0), (R - 5, off, 0.5), (R + 5, off, 0.5)):
            dx, dy = int(round(rr * c)), int(round(rr * s))
            acc += wgt * A[P + dy:P + dy + H, P + dx:P + dx + W]
    return (on - off) / angles


def find_ring(img, k_lo, k_hi):
    """화면 왼쪽 위 조각(img · PIL)에서 미니맵 테두리 찾기 → (가운데 x, 가운데 y, 반지름, 점수) · 반지름은 184·k_lo ~ 184·k_hi 사이"""
    f = max(1, int(RING_R * k_lo / 40))                     # 반지름이 약 40px 이 되게 줄여서 먼저 넓게
    g = img.convert('L'); full = np.asarray(g, np.float32) / 255
    # 얇은 테두리가 줄일 때 흐려지지 않게: 주변 평균을 뺀 '밝은 선'만 남기고(고주파) f×f 칸의 최댓값으로 줄임
    hp = full - np.asarray(g.filter(ImageFilter.BoxBlur(4)), np.float32) / 255
    H2, W2 = hp.shape[0] // f, hp.shape[1] // f
    a = hp[:H2 * f, :W2 * f].reshape(H2, f, W2, f).max(axis=(1, 3)) if f > 1 else hp
    best = (-1, 0, 0, 0)
    for R in range(max(6, int(RING_R * k_lo / f * 0.92)), int(RING_R * k_hi / f * 1.08) + 1):
        s = ring_score(a, R); iy, ix = np.unravel_index(int(np.argmax(s)), s.shape)
        if s[iy, ix] > best[0]:
            best = (float(s[iy, ix]), ix * f, iy * f, R * f)
    sc, cx, cy, R = best
    if f > 1:                                               # 원래 크기에서 둘레만 다시
        x0, y0 = max(0, cx - R - 3 * f), max(0, cy - R - 3 * f)
        a = np.asarray(g.crop((x0, y0, min(g.width, cx + R + 3 * f), min(g.height, cy + R + 3 * f))), np.float32) / 255
        best = (-1, 0, 0, 0)
        for R2 in range(R - 2 * f, R + 2 * f + 1):
            s = ring_score(a, R2, 96); m = np.zeros_like(s, bool); m[max(0, cy - y0 - 2 * f):cy - y0 + 2 * f + 1, max(0, cx - x0 - 2 * f):cx - x0 + 2 * f + 1] = True
            s = np.where(m, s, -1); iy, ix = np.unravel_index(int(np.argmax(s)), s.shape)
            if s[iy, ix] > best[0]:
                best = (float(s[iy, ix]), x0 + ix, y0 + iy, R2)
        sc, cx, cy, R = best
    return cx, cy, R, sc


def icon_mask(t, m):
    """비교 마스크 m 에서 게임 미니맵 위에 겹친 아이콘(내 위치 화살표 · NPC · 퀘스트 표시 · 빨간 경로선)을 뺌 — 지도 그림에는 없는 것
    t = feat() 결과(밝기 · 빨강−초록 · 파랑−초록): 아주 밝은 흰 테두리 · 진한 빨강/주황 · 진한 파랑은 아이콘으로 봄 (둘레 1px 까지)"""
    L, rg, bg = t
    ic = (L > 0.86) | (rg > 0.30) | (bg > 0.28)
    ic = ic | np.roll(ic, 1, 0) | np.roll(ic, -1, 0) | np.roll(ic, 1, 1) | np.roll(ic, -1, 1)
    out = m * (~ic)
    return out if out.sum() > m.sum() * 0.5 else m          # 아이콘이 절반 넘게 가리면(이상한 화면) 그대로


def feat(im):
    a = np.asarray(im.convert('RGB'), np.float32) / 255
    return np.stack([a.mean(2), a[..., 0] - a[..., 1], a[..., 2] - a[..., 1]], 0)


def ring(size, r0=0.30, r1=0.92):
    yy, xx = np.mgrid[:size, :size]
    r = np.hypot(xx - size / 2 + .5, yy - size / 2 + .5) / (size / 2)
    return ((r < r1) & (r > r0)).astype(np.float32)


def ncc(I, t, m):
    """I (C,H,W) 안에서 t (C,h,w · 마스크 m) 와 가장 닮은 곳 — 점수 지도 (H-h+1, W-w+1)"""
    C, H, W = I.shape; h, w = m.shape; n = m.sum()
    F = lambda x: np.fft.rfft2(x, (H, W))
    Fm = np.conj(F(m)); num = 0; den_i = 0; den_t = 0
    for c in range(C):
        tc = (t[c] - (t[c] * m).sum() / n) * m
        Fi = F(I[c])
        num = num + np.fft.irfft2(Fi * np.conj(F(tc)), (H, W))
        s1 = np.fft.irfft2(Fi * Fm, (H, W)); s2 = np.fft.irfft2(F(I[c] ** 2) * Fm, (H, W))
        den_i = den_i + np.maximum(s2 - s1 ** 2 / n, 1e-6); den_t += float((tc ** 2).sum())
    return (num / np.sqrt(den_i * max(den_t, 1e-9)))[:H - h + 1, :W - w + 1]


def texture(patch):
    """미니맵 조각의 무늬 양 (이웃 화소 밝기 차이 평균) — 메뉴 · 흐린 화면처럼 밋밋하면 낮음 (미니맵 0.05~0.07 · 메뉴 화면 0.01)"""
    t = feat(patch.resize((64, 64), Image.BILINEAR))[0]; m = ring(64) > 0
    return float(np.abs(np.diff(t, axis=1))[m[:, 1:]].mean() + np.abs(np.diff(t, axis=0))[m[1:, :]].mean())


def peak(s):
    iy, ix = np.unravel_index(int(np.argmax(s)), s.shape); v = float(s[iy, ix])
    dx = dy = 0.0                                         # 꼭대기 둘레 3점으로 소수점 자리까지
    if 0 < ix < s.shape[1] - 1:
        a, b, c = s[iy, ix - 1], v, s[iy, ix + 1]; d = a - 2 * b + c; dx = float(0.5 * (a - c) / d) if d else 0.0
    if 0 < iy < s.shape[0] - 1:
        a, b, c = s[iy - 1, ix], v, s[iy + 1, ix]; d = a - 2 * b + c; dy = float(0.5 * (a - c) / d) if d else 0.0
    return v, ix + dx, iy + dy


class MapData:
    def __init__(self, m, cache):
        self.id, self.name = str(m['id']), m['name']
        self.size, self.xf, self.h = m['size'], m.get('xf') or [0, 0, m['size'][0], m['size'][1], 0], m.get('h')
        self.tex = m.get('tex')            # 게임 지도 그림 가로 화소 (미니맵 축척 계산)
        d = os.path.join(cache, self.id)
        base = Image.open(os.path.join(d, 'base.webp')).convert('RGB')
        self.fc = feat(base.resize((COARSE, COARSE), Image.BILINEAR))
        self.ff = feat(base.resize((FINE, FINE), Image.BILINEAR)) if base.width >= FINE else feat(base.resize((FINE, FINE), Image.BICUBIC))
        self.hm = None
        hp = os.path.join(d, 'h.webp')
        if self.h and os.path.exists(hp):
            a = np.asarray(Image.open(hp).convert('RGB'), np.float32)
            self.hm = (a[..., 0] * 256 + a[..., 1]) / 65535 * (self.h['max'] - self.h['min']) + self.h['min']

    def world(self, u, v):
        """지도 그림 위치(0~1) → 월드 (x, y, z)"""
        ox, oz, sw, sh, rot = self.xf; r = math.radians(rot); du, dv = u - 0.5, v - 0.5
        a, b = du * math.cos(r) + dv * math.sin(r), -du * math.sin(r) + dv * math.cos(r)
        y = 0.0
        if self.hm is not None:
            n = self.hm.shape[0]; y = float(self.hm[min(n - 1, max(0, int(round(v * (n - 1))))), min(n - 1, max(0, int(round(u * (n - 1)))))])
        return a * sw + ox, y, -b * sh + oz


def ensure_cache(cache, log=lambda s: None):
    """지도 자료를 사이트에서 받아 exe 옆 maps/ 에 보관 (data.json 은 매번 새로 · 그림은 없을 때만)"""
    os.makedirs(cache, exist_ok=True)
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'PromiliaTracker2'}), timeout=30).read()
    dj = os.path.join(cache, 'data.json')
    try:
        log('지도 목록을 받는 중…'); raw = get(BASE + 'data.json'); open(dj, 'wb').write(raw)
    except Exception:
        if not os.path.exists(dj):
            raise
    D = json.load(open(dj, encoding='utf-8'))
    for m in D['maps']:
        d = os.path.join(cache, str(m['id'])); os.makedirs(d, exist_ok=True)
        for f in ['base.webp'] + (['h.webp'] if m.get('h') else []):
            p = os.path.join(d, f)
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                log(f"{m['name']} 지도 그림을 받는 중…"); open(p, 'wb').write(get(BASE + f"{m['id']}/{f}"))
    return D


class Locator:
    def __init__(self, cache, log=lambda s: None, px_per_m=MM_PX_PER_M):
        D = ensure_cache(cache, log)
        log('지도 그림을 준비하는 중…')
        self.maps = [MapData(m, cache) for m in D['maps']]
        self.px_per_m = px_per_m
        self.cur = None            # (MapData, u, v) — 붙어 있는 위치
        self.geom = None           # 화면에서 찾은 미니맵 테두리 (가운데 x, 가운데 y, 반지름) · 게임 창 안쪽 좌표
        self.info = {}             # 마지막으로 못 찾은 이유와 점수 (진단 로그용 · diag.py)
        self.cand = {}             # 마지막 테두리 후보 (자리 · 점수 · 버린 이유) — 진단 로그용

    def detect(self, grab, w, h):
        """게임 화면에서 미니맵 테두리를 찾아 자리를 정함 (창 크기가 바뀌거나 오래 못 찾을 때) — grab(box) 는 창 안쪽 좌표로 캡처
        21:9 등 넓은 화면: 게임이 UI 를 16:9 영역 안에 가운데로 모으든 왼쪽에 붙이든 찾음 · 16:10 등 좁은 화면: 가로 비례도 함께 봄"""
        kh, kw = h / 2160, w / 3840; k_lo, k_hi = min(kh, kw) * 0.85, max(kh, kw) * 1.15
        side = max(0, (w - h * 16 / 9) / 2)                  # 16:9 보다 넓으면 가운데 정렬 때 왼쪽 여백
        rw, rh = int(min(w, side + (RING_CX + RING_R) * k_hi + 40)), int(min(h, (RING_CY + RING_R) * k_hi + 40))
        cx, cy, R, sc = find_ring(grab((0, 0, rw, rh)), k_lo, k_hi)
        ok, why = sc > 0.06, '' if sc > 0.06 else '테두리 점수 낮음'
        if ok:   # 11-28: 자리 · 크기가 말이 되는지 — 1080p 진단에서 배경의 밝은 무늬(점수 0.09~0.10)를 테두리로 잡아 미니맵 대신 풀숲을 자르던 것
            ok, why = self.plausible(cx, cy, R, w, h)
        self.cand = {'at': [int(cx), int(cy), int(R)], 'score': round(float(sc), 3), 'why': why}
        self.geom = (cx, cy, R) if ok else None
        return self.geom, sc

    @staticmethod
    def expected(w, h):
        """화면 비율로 본 미니맵 테두리의 예상 자리들 [(가운데 x, 가운데 y, 반지름)] — 세로 비례 · 가로 비례 · 넓은 화면 가운데 정렬"""
        kh, kw = h / 2160, w / 3840; side = max(0, (w - h * 16 / 9) / 2); out = []
        for k, dx in ((kh, 0), (kw, 0), (kh, side)):
            out.append((dx + RING_CX * k, RING_CY * k, RING_R * k))
        return out

    def plausible(self, cx, cy, R, w, h):
        """찾은 테두리가 예상 자리 중 하나와 가까운지(가운데 거리 ≤ 예상 반지름의 45%) · 크기가 비슷한지(0.75 ~ 1.3배)"""
        best = min(self.expected(w, h), key=lambda e: math.hypot(cx - e[0], cy - e[1]))
        ex, ey, er = best
        if math.hypot(cx - ex, cy - ey) > er * 0.45:
            return False, f'예상 자리({ex:.0f},{ey:.0f})와 멂'
        if not (er * 0.75 <= R <= er * 1.3):
            return False, f'크기가 예상({er:.0f})과 다름'
        return True, ''

    def crop_box(self, w, h, use_geom=True):
        """게임 화면(클라이언트 영역 w×h)에서 미니맵을 자를 자리 — 찾은 테두리가 있으면 그 기준(비교 반지름 = 테두리 × 150/184)
        use_geom=False 면 찾은 테두리를 무시하고 기본 자리(세로 비례 · 왼쪽 위) — 찾은 자리로 계속 실패할 때 번갈아 시험 (tracker2.py)"""
        if self.geom and use_geom:
            cx, cy, R = self.geom; r = R * MM_R / RING_R
            return int(round(cx - r)), int(round(cy - r)), int(round(cx + r)), int(round(cy + r))
        k = h / 2160
        return int((MM_CX - MM_R) * k), int((MM_CY - MM_R) * k), int((MM_CX + MM_R) * k), int((MM_CY + MM_R) * k)

    def ppm(self, mp):
        """이 지도의 미니맵 축척 (세로 2160 화면에서 1m 당 px) — 지도 그림 화소 밀도에 비례 · 설정 px_per_m 은 새싹 골짜기 기준값으로 보고 같은 비율로 맞춤"""
        return self.px_per_m / MM_PX_PER_M * MM_TEX_K * mp.tex / mp.size[0] if mp.tex else self.px_per_m

    def tsize(self, mp, res, scale=1.0):
        """미니맵 조각(지름 2·MM_R)이 지도 그림(res px)에서 차지하는 크기"""
        return 2 * MM_R / (self.ppm(mp) * scale) / mp.size[0] * res

    def coarse(self, patch, maps=None):
        best = None
        for mp in (maps or self.maps):
            size = max(12, int(round(self.tsize(mp, COARSE))))
            if size > COARSE // 2:
                continue
            t = feat(patch.resize((size, size), Image.BILINEAR)); sc = ncc(mp.fc, t, icon_mask(t, ring(size))); v, x, y = peak(sc)
            # 한 곳만 뚜렷하게 맞아야 함: 가장 높은 곳을 가린 뒤의 둘째 점수와 비교 (진짜 미니맵 1.5배 이상 · 오인식 1.0~1.2배)
            ix, iy, r = int(round(x)), int(round(y)), max(4, size // 2); s2 = sc.copy(); s2[max(0, iy - r):iy + r + 1, max(0, ix - r):ix + r + 1] = -1
            uniq = v / max(float(s2.max()), 1e-6)
            if not best or v > best[0]:
                best = (v, mp, (x + size / 2) / COARSE, (y + size / 2) / COARSE, uniq)
        return best

    def fine(self, patch, mp, u, v, win=0.035):
        """(u, v) 둘레 ±win 안에서 2048 그림으로 정밀하게"""
        size = max(16, int(round(self.tsize(mp, FINE)))); half = size / 2; w = int(win * FINE)
        x0, y0 = int(round(u * FINE - half - w)), int(round(v * FINE - half - w)); n = size + 2 * w
        x0, y0 = max(0, min(FINE - n, x0)), max(0, min(FINE - n, y0))
        I = mp.ff[:, y0:y0 + n, x0:x0 + n]
        t = feat(patch.resize((size, size), Image.BILINEAR)); s, x, y = peak(ncc(I, t, icon_mask(t, ring(size))))
        return s, (x0 + x + half) / FINE, (y0 + y + half) / FINE

    def locate(self, patch):
        """미니맵 조각 → (점수, MapData, u, v) 또는 None. 붙어 있으면 둘레만, 아니면 전체에서"""
        tx = texture(patch)
        if tx < 0.03:                                      # 밋밋한 화면(메뉴 · 로딩 · 가려짐) — 미니맵이 아님
            self.cur = None; self.info = {'why': '밋밋한 화면(메뉴·로딩·가려짐)', 'tex': round(tx, 3)}; return None
        if self.cur:
            mp, u, v = self.cur
            s, u2, v2 = self.fine(patch, mp, u, v)
            if s >= 0.5:
                self.cur = (mp, u2, v2); return s, mp, u2, v2
            self.cur = None
        c = self.coarse(patch)
        # 전체에서 찾을 때는 점수가 높고(0.6↑) 한 곳만 뚜렷해야(둘째의 1.25배↑) 바로 붙음
        # 11-28: 덜 뚜렷한 경우(1.1 ~ 1.25배)는 정밀 점수가 0.62↑ 이고 연속 두 번 같은 자리(지도 그림 1% 안)일 때 붙음
        #   — 3440×1440 진단: 맞는 자리(새싹 골짜기)를 찾았는데 둘째의 1.20배라 계속 버려지던 것 (사이트 지도 그림이 2048px 라 미니맵보다 흐림)
        if not c or c[0] < 0.6 or c[4] < 1.1:
            self.info = {'why': '지도와 맞는 곳 없음', 'tex': round(tx, 3), 'best_map': c[1].name if c else None, 'score': round(c[0], 3) if c else None, 'uniq': round(c[4], 2) if c else None}
            return None
        s0, mp, u, v, uq = c
        s, u2, v2 = self.fine(patch, mp, u, v, win=0.02)
        if s < (0.55 if uq >= 1.25 else 0.62):
            self.info = {'why': '정밀 맞추기 실패', 'map': mp.name, 'coarse': round(s0, 3), 'fine': round(s, 3), 'uniq': round(uq, 2)}
            return None
        if uq < 1.25:
            p = getattr(self, 'pend', None)
            # 사이에 다른 자리(번갈아 시험하는 기본 자리 등)에서 실패해도 4초 안이면 이어서 봄
            if not (p and p[0] is mp and math.hypot(p[1] - u2, p[2] - v2) < 0.01 and time.time() - p[3] < 4):
                self.pend = (mp, u2, v2, time.time())
                self.info = {'why': '후보 확인 중(한 번 더 같은 자리면 붙음)', 'map': mp.name, 'coarse': round(s0, 3), 'fine': round(s, 3), 'uniq': round(uq, 2)}
                return None
        self.pend = None
        self.cur = (mp, u2, v2); self.info = {}
        return s, mp, u2, v2
