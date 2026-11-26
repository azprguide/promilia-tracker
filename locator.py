"""화면의 미니맵 → 지도 위 위치 (메모리를 읽지 않음)

게임 화면 왼쪽 위의 둥근 미니맵을 잘라, 프로밀리아 가이드의 지도 그림(/img/g/map/<지도>/base.webp)에서 같은 곳을 찾는다.
- 비교: 마스크를 씌운 정규화 상관(밝기 + 색 차이 2개) — numpy FFT 로 계산 (OpenCV 없이)
- 처음 · 놓쳤을 때: 지도 전체에서 찾음(지도마다 1024px 로 줄인 그림) → 붙은 뒤: 직전 위치 둘레만 2048px 그림에서 찾음(빠르고 정밀)
- 미니맵은 반투명이고 가운데에 캐릭터 표시가 있어, 고리 모양(안쪽 30% ~ 바깥 92%)만 비교
- 좌표: 지도 그림 위치(u, v) → 월드 좌표 = 사이트 map.html toUV 의 역변환 (data.json maps[].xf = [ox, oz, 가로, 세로, 회전])
- 높이(y): 3D 보기용 지형 높이 그림(h.webp · 16비트)에서 읽음 (없으면 0)
"""
import io, json, math, os, urllib.request
import numpy as np
from PIL import Image

SITE = 'https://azur-promilia.pages.dev'
BASE = SITE + '/img/g/map/'
# 미니맵 자리 · 크기 (세로 2160 화면 기준 px — 화면 세로에 비례): 가운데 (285, 245) · 비교에 쓰는 반지름 150
MM_CX, MM_CY, MM_R = 285, 245, 150
# 미니맵 축척: 세로 2160 화면에서 1m 가 몇 px 인지 (새싹 골짜기에서 잰 값 · calibrate 로 다시 잴 수 있음)
MM_PX_PER_M = 3.45
COARSE, FINE = 1024, 2048


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

    def crop_box(self, w, h):
        """게임 화면(클라이언트 영역 w×h)에서 미니맵을 자를 자리"""
        k = h / 2160
        return int((MM_CX - MM_R) * k), int((MM_CY - MM_R) * k), int((MM_CX + MM_R) * k), int((MM_CY + MM_R) * k)

    def tsize(self, mp, res, scale=1.0):
        """미니맵 조각(지름 2·MM_R)이 지도 그림(res px)에서 차지하는 크기"""
        return 2 * MM_R / (self.px_per_m * scale) / mp.size[0] * res

    def coarse(self, patch, maps=None):
        best = None
        for mp in (maps or self.maps):
            size = max(12, int(round(self.tsize(mp, COARSE))))
            if size > COARSE // 2:
                continue
            t = feat(patch.resize((size, size), Image.BILINEAR)); sc = ncc(mp.fc, t, ring(size)); v, x, y = peak(sc)
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
        t = feat(patch.resize((size, size), Image.BILINEAR)); s, x, y = peak(ncc(I, t, ring(size)))
        return s, (x0 + x + half) / FINE, (y0 + y + half) / FINE

    def locate(self, patch):
        """미니맵 조각 → (점수, MapData, u, v) 또는 None. 붙어 있으면 둘레만, 아니면 전체에서"""
        if texture(patch) < 0.03:                          # 밋밋한 화면(메뉴 · 로딩 · 가려짐) — 미니맵이 아님
            self.cur = None; return None
        if self.cur:
            mp, u, v = self.cur
            s, u2, v2 = self.fine(patch, mp, u, v)
            if s >= 0.5:
                self.cur = (mp, u2, v2); return s, mp, u2, v2
            self.cur = None
        c = self.coarse(patch)
        if not c or c[0] < 0.6 or c[4] < 1.25:             # 전체에서 찾을 때는 점수가 높고(0.6↑) 한 곳만 뚜렷해야(둘째의 1.25배↑) 붙음
            return None
        s0, mp, u, v, _ = c
        s, u2, v2 = self.fine(patch, mp, u, v, win=0.02)
        if s < 0.55:
            return None
        self.cur = (mp, u2, v2)
        return s, mp, u2, v2
