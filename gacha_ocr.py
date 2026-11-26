"""관측 기록 모으기 — 화면 글자 인식(OCR) 방식 (2026-11-26 · 트래커 2)

게임의 '관측 → 확률 설명 → 기록' 화면이 보이면 표(유형 · 이름 · 카드풀 이름 · 뽑기 시간)를 캡처해 Windows 내장 OCR(한국어)로 읽어 모은다.
게임 메모리 · 통신을 건드리지 않음. 읽은 이름은 사이트 관측 자료(gacha.json)의 이름 목록과 맞춰 번호로 바꿈.

- OCR: Windows.Media.Ocr 를 숨은 Windows PowerShell 한 개로 계속 띄워 두고 그림 파일 경로를 보내 결과(낱말 · 자리)를 받음
- 화면 찾기: 표 머리줄(어두운 회색 띠) 자리의 색으로 먼저 확인 → 맞을 때만 OCR (1초에 한 번쯤)
- 한 페이지 5줄. 페이지 번호는 꾸민 글꼴이라 읽히지 않아, 페이지 순서는 '넘긴 순서 + 시각'으로 맞춤:
    다음 쪽으로 넘기면 시각이 같거나 더 옛날 · 이전 쪽이면 같거나 더 최근 — 같은 분끼리면 직전에 넘기던 방향을 따름
- 저장: 관측 종류마다 최근 → 옛날 순서의 목록. 다시 읽을 때는 '같은 분(시각)의 줄 수가 더 많은 쪽'을 믿고 바꿈(중복으로 늘지 않음)
- 시각은 분 단위(화면 표시) · 기록 번호가 화면에 없어 사이트로 보낼 때 r = 시각×100000 + 배너 번호, s = 그 분 안의 순번으로 만듦
- UID 는 화면 왼쪽 아래 'UID:…' 글자를 읽음
"""
import difflib, json, os, re, subprocess, tempfile, threading, time, urllib.request, calendar

SITE = 'https://azur-promilia.pages.dev'
ROWS = 5
# 화면 자리 (1280×720 기준 · 화면 가운데에서의 거리로 계산 — 창은 화면 가운데에 뜸): 표 = x 327~1075 · y 277~476 (머리줄 22 + 줄 35.4×5)
TBL = (327, 277, 1075, 476)
HEAD_H = 22.0
COLS = (93, 358, 546)            # 표 안에서 칸이 나뉘는 x (유형 | 이름 | 카드풀 이름 | 뽑기 시간)
UID_BOX = (80, 698, 270, 720)    # 왼쪽 아래 (왼쪽 · 아래 기준)

PS_SERVER = r'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Console]::InputEncoding = [Text.Encoding]::UTF8
$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))
if (-not $eng) { 'NOENGINE'; exit 1 }
'READY'
while (($path = [Console]::In.ReadLine()) -ne $null) {
  if ($path -eq 'q') { break }
  try {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    $ws = @(); foreach ($l in $res.Lines) { foreach ($w in $l.Words) { $ws += ,@($w.Text, [int]$w.BoundingRect.X, [int]$w.BoundingRect.Y, [int]$w.BoundingRect.Width, [int]$w.BoundingRect.Height) } }
    $bmp.Dispose(); $stream.Dispose(); $file = $null; $dec = $null; [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    if ($ws.Count) { ConvertTo-Json -InputObject $ws -Compress } else { '[]' }
  } catch { '[]' }
  [Console]::Out.Flush()
}
'''


class Ocr:
    """숨은 PowerShell 로 Windows OCR 을 부름 (한 번 띄워 계속 씀)"""
    def __init__(self):
        self.p = None; self.dir = tempfile.mkdtemp(prefix='pgtrk2_'); self.lock = threading.Lock(); self.err = ''

    def start(self):
        if self.p and self.p.poll() is None:
            return True
        script = os.path.join(self.dir, 'ocr.ps1'); open(script, 'w', encoding='utf-8-sig').write(PS_SERVER)
        try:
            self.p = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding='utf-8', errors='replace',
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            first = self.p.stdout.readline().strip()
            if first != 'READY':
                self.err = 'Windows 한국어 글자 인식(OCR)을 쓸 수 없어요 — 설정 → 시간 및 언어 → 언어에서 한국어 언어 팩을 확인해 주세요'; self.stop(); return False
            return True
        except Exception as e:
            self.err = f'글자 인식을 시작하지 못했어요: {type(e).__name__}'; self.p = None; return False

    def read(self, img):
        """PIL 그림 → [(글자, x, y, w, h)]"""
        with self.lock:
            if not self.start():
                return None
            self.n = getattr(self, 'n', 0) + 1
            path = os.path.join(self.dir, f'cap{self.n}.png')                      # 방금 읽은 파일은 잠시 잠겨 있을 수 있어 매번 새 이름 · 예전 것은 지움
            try:
                os.remove(os.path.join(self.dir, f'cap{self.n - 3}.png'))
            except OSError:
                pass
            try:
                img.save(path)
                self.p.stdin.write(path + '\n'); self.p.stdin.flush(); out = self.p.stdout.readline()
                d = json.loads(out) if out.strip() else []
                return [tuple(w) for w in (d if d and isinstance(d[0], list) else ([d] if d else []))]
            except Exception:
                self.stop(); return None

    def stop(self):
        try:
            if self.p:
                self.p.stdin.write('q\n'); self.p.stdin.flush(); self.p.kill()
        except Exception:
            pass
        self.p = None


class Names:
    """사이트 관측 자료: 이름 → 아이템 키(h101010 · s…) · 배너 이름 → (번호, 종류)"""
    def __init__(self, cache):
        p = os.path.join(cache, 'gacha.json'); os.makedirs(cache, exist_ok=True)
        try:
            raw = urllib.request.urlopen(urllib.request.Request(SITE + '/img/g/codex/gacha.json', headers={'User-Agent': 'PromiliaTracker2'}), timeout=30).read(); open(p, 'wb').write(raw)
        except Exception:
            if not os.path.exists(p):
                raise
        G = json.load(open(p, encoding='utf-8'))
        self.items = {}
        for k, it in G['items'].items():
            if k[:1] in ('h', 's') and k[1:].isdigit() and it.get('name'):
                self.items.setdefault(it['name'], (k, it.get('star') or 0))
        self.pools = {b['name']: (b['id'], b['type']) for b in G['banners']}
        self.pool_name = {b['id']: b['name'] for b in G['banners']}; self.type_name = {b['type']: b['typeName'] for b in G['banners']}

    @staticmethod
    def near(s, keys, cut=0.6):
        s = re.sub(r'\s+', '', s)
        table = {re.sub(r'\s+', '', k): k for k in keys}
        if s in table:
            return table[s]
        m = difflib.get_close_matches(s, list(table), n=1, cutoff=cut)
        return table[m[0]] if m else None


class GH:
    St = None; path = ''; data = {'v': 1, 'app': 'promilia-tracker2', 'uid': '', 'types': {}}   # types: {'<종류>': [줄(최근 → 옛날)…]} · 줄 = {i, t, p, at}
    names = None; ocr = Ocr(); lock = threading.Lock()
    chain = None      # 지금 넘기고 있는 묶음: {'type', 'pages': [[줄…]…], 'ptr', 'dir'}
    bad = 0


def load():
    try:
        d = json.load(open(GH.path, encoding='utf-8'))
        if d.get('app') == 'promilia-tracker2' and isinstance(d.get('types'), dict):
            GH.data = d
    except Exception:
        pass


def save():
    try:
        tmp = GH.path + '.tmp'; json.dump(GH.data, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':')); os.replace(tmp, GH.path)
    except Exception:
        pass


def count():
    return sum(len(v) for v in GH.data['types'].values())


def groups(rows):
    """최근 → 옛날 순서의 줄들을 같은 분끼리 묶음 → [(at, [줄…])…]"""
    out = []
    for r in rows:
        if out and out[-1][0] == r['at']:
            out[-1][1].append(r)
        else:
            out.append((r['at'], [r]))
    return out


def chrono(grp):
    """같은 분의 줄들(화면 순서 = 위에서 아래)을 관측한 순서(옛날 → 최근)로.
    게임 화면은 최근 관측이 위지만, 10회 관측 한 번 안에서는 뽑힌 순서대로(첫 번째가 위) 보여 줌(트래커 1 의 기록 순번과 대조해 확인 · 11-26)
    → 10줄씩 한 묶음으로 보고 묶음 순서만 뒤집음. 줄 수가 10의 배수가 아니면 1회 관측이 섞인 것이라 묶음을 알 수 없어, 위에서부터 10줄씩 자르고 남는 줄은 1회 관측으로 봄"""
    blocks = [grp[i:i + 10] for i in range(0, len(grp) - len(grp) % 10, 10)] + [[r] for r in grp[len(grp) - len(grp) % 10:]]
    return [r for b in reversed(blocks) for r in b]


def merge(ty, scanned):
    """방금 읽은 줄들(최근 → 옛날)을 저장된 목록에 합침: 같은 분은 줄 수가 더 많은 쪽을 씀 → 새로 늘어난 줄 수"""
    old = GH.data['types'].get(str(ty), []); before = len(old)
    g = {at: rows for at, rows in groups(old)}
    for at, rows in groups(scanned):
        if len(rows) > len(g.get(at, [])):
            g[at] = rows
    new = [r for at in sorted(g, reverse=True) for r in g[at]]
    GH.data['types'][str(ty)] = new
    return len(new) - before


def parse(words, scale):
    """OCR 낱말 → 표의 줄들 [(유형, 이름, 등급, 카드풀, 'YYYY-MM-DD HH:MM')] (빈 줄은 뺌) · 표가 아니면 None"""
    cells = {}
    for t, x, y, w, h in words:
        cy = (y + h / 2) / scale - HEAD_H; cx = (x + w / 2) / scale
        row = -1 if cy < 0 else int(cy // ((TBL[3] - TBL[1] - HEAD_H) / ROWS))
        col = 0 if cx < COLS[0] else 1 if cx < COLS[1] else 2 if cx < COLS[2] else 3
        cells.setdefault((row, col), []).append((x, t))
    txt = lambda r, c: ' '.join(t for _, t in sorted(cells.get((r, c), [])))
    head = txt(-1, 1) + txt(-1, 2) + txt(-1, 3)
    if '이름' not in head or '시간' not in head:
        return None
    rows = []
    for r in range(ROWS):
        kind, name, pool, tm = (txt(r, c).strip() for c in range(4))
        if not (kind or name or pool or tm):
            continue
        m = re.match(r'^(.*?)\s*[\(（]\s*(\d)\s*성\s*[\)）]?$', name); star = int(m.group(2)) if m else 0; nm = m.group(1).strip() if m else name
        t = re.sub(r'[^\d]', '', tm)
        rows.append((kind, nm, star, pool, f'{t[:4]}-{t[4:6]}-{t[6:8]} {t[8:10]}:{t[10:12]}' if len(t) == 12 else ''))
    return rows


def to_records(rows):
    """읽은 줄 → 저장 형식. 이름 · 배너를 자료와 맞추지 못한 줄이 있으면 None (그 화면은 다시 읽음)"""
    N = GH.names; out = []
    for kind, nm, star, pool, tm in rows:
        if not tm:
            return None
        name = N.near(nm, N.items); pn = N.near(pool, N.pools, 0.5)
        if not name or not pn:
            return None
        key, st = N.items[name]; pid, ty = N.pools[pn]
        try:
            at = calendar.timegm(time.strptime(tm, '%Y-%m-%d %H:%M')) - 9 * 3600      # 화면 시각 = 한국 시간
        except ValueError:
            return None
        out.append({'i': int(key[1:]), 't': 1 if key[0] == 'h' else 2, 'p': pid, 'at': at, 'g': ty})
    return out


def feed(page):
    """안정적으로 읽힌 한 페이지(줄 목록 · 최근 → 옛날)를 묶음에 넣고 저장 목록에 합침"""
    if not page:
        return
    ty = page[0]['g']; sig = lambda p: [(r['i'], r['t'], r['p'], r['at']) for r in p]
    c = GH.chain
    if not c or c['type'] != ty:
        c = GH.chain = {'type': ty, 'pages': [page], 'ptr': 0, 'dir': 1}
    else:
        cur = c['pages'][c['ptr']]
        if sig(cur) == sig(page):
            return
        nxt = c['pages'][c['ptr'] + 1] if c['ptr'] + 1 < len(c['pages']) else None; prv = c['pages'][c['ptr'] - 1] if c['ptr'] > 0 else None
        known = next((k for k, pg in enumerate(c['pages']) if sig(pg) == sig(page)), -1)
        if nxt is not None and sig(nxt) == sig(page):
            c['ptr'] += 1; c['dir'] = 1
        elif prv is not None and sig(prv) == sig(page):
            c['ptr'] -= 1; c['dir'] = -1
        elif known >= 0:                                   # 이미 읽은 쪽으로 건너옴(예: 종류를 다시 눌러 1쪽으로) — 새로 끼워 넣지 않고 그 자리로
            c['dir'] = 1 if known > c['ptr'] else -1; c['ptr'] = known
        else:
            older = max(r['at'] for r in page) <= min(r['at'] for r in cur); newer = min(r['at'] for r in page) >= max(r['at'] for r in cur)
            d = c['dir'] if older and newer else 1 if older else -1 if newer else c['dir']
            if d > 0:
                c['pages'].insert(c['ptr'] + 1, page); c['ptr'] += 1
            else:
                c['pages'].insert(c['ptr'], page)
            c['dir'] = d
    flat = [dict(r) for p in c['pages'] for r in p]
    with GH.lock:
        new = merge(ty, flat); save()
    GH.St.gacha_count = count()
    tn = GH.names.type_name.get(ty, '관측')
    GH.St.gacha_status = f'{tn} 기록을 읽는 중 — 이번에 {len(c["pages"])}쪽 읽음' + (f' · 새 기록 {new}건' if new > 0 else '') + ' · 다음 쪽(→)으로 넘겨 주세요'


def dbg(kind, rows=None, img=None, extra=''):
    """읽기 일지 (exe 옆 ocr-debug/log.txt · 실패한 쪽은 그림도 같이, 최근 60장까지) — 인식이 안 될 때 원인을 보려고 남김. 이 PC 안에만 있음"""
    try:
        d = os.path.join(os.path.dirname(GH.path), 'ocr-debug'); os.makedirs(d, exist_ok=True)
        GH.dn = getattr(GH, 'dn', 0) + 1
        with open(os.path.join(d, 'log.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{time.strftime('%H:%M:%S')} #{GH.dn} {kind} {extra} {json.dumps(rows, ensure_ascii=False) if rows is not None else ''}\n")
        if img is not None:
            img.save(os.path.join(d, f'p{GH.dn % 60:02d}.png'))
    except Exception:
        pass


def boxes(w, h):
    """게임 화면(w×h) 안의 표 · UID 자리 (화면 가운데 기준 · 세로에 비례)"""
    k = h / 720; cx, cy = w / 2, h / 2
    tb = tuple(int(round(v)) for v in (cx + (TBL[0] - 640) * k, cy + (TBL[1] - 360) * k, cx + (TBL[2] - 640) * k, cy + (TBL[3] - 360) * k))
    ub = tuple(int(round(v)) for v in (UID_BOX[0] * k, h - (720 - UID_BOX[1]) * k, UID_BOX[2] * k, h))
    return tb, ub, k


def looks_like_table(img):
    """표 머리줄(어두운 회색 띠) + 그 아래 밝은 줄인지 — 색만 보고 빠르게 판단"""
    w, h = img.size; y1 = int(h * 0.055); y2 = int(h * 0.92)
    dark = [img.getpixel((int(w * f), y1)) for f in (0.03, 0.25, 0.47, 0.62, 0.97)]
    light = [img.getpixel((int(w * f), y2)) for f in (0.03, 0.5, 0.97)]
    isdark = lambda p: max(p[:3]) < 130 and max(p[:3]) - min(p[:3]) < 30
    return sum(isdark(p) for p in dark) >= 4 and sum(min(p[:3]) > 170 for p in light) >= 2


def loop(game_rect):
    """캡처와 글자 인식을 나눠서 돌림 (0.2.6) — 빠르게 넘겨도 쪽을 놓치지 않게:
    · 캡처(이 함수 · 약 0.03초마다): 표가 '멈춘' 화면(직전 캡처와 같음)이고 마지막으로 줄 세운 화면과 다르면 그림을 줄에 넣음
    · 인식(ocr_worker · 한 장에 약 0.2초): 줄에 쌓인 그림을 넘긴 순서대로 읽어 합침 — 넘기는 속도가 인식보다 빨라도 그림은 남아 있어 뒤따라 읽음"""
    import capture, collections
    St = GH.St; q = collections.deque(); wait = 1.0; gone = 0; prev = None; queued = None; moving = 0; active = False
    small = lambda im: im.resize((748, 199)).convert('L').tobytes()                # 글자만 바뀐 쪽도 구분되는 크기
    same = lambda a, b: a is not None and b is not None and sum(abs(x - y) > 16 for x, y in zip(a, b)) < 12
    threading.Thread(target=ocr_worker, args=(q, game_rect), daemon=True).start()
    while not St.quit:
        time.sleep(wait)
        r = game_rect()
        if not r:
            wait = 1.0; continue
        x, y, w, h = r; tb, ub, k = boxes(w, h)
        try:
            img = capture.grab((x + tb[0], y + tb[1], x + tb[2], y + tb[3]))
        except Exception:
            continue
        if not looks_like_table(img):
            # 쪽을 넘기는 순간에는 표가 잠깐 안 보임 — 2초 넘게 안 보일 때만 '기록 화면을 닫았다'로 보고 이어 붙이기(묶음)를 끝냄
            gone = gone or time.time(); prev = None
            if time.time() - gone > 2.0:
                if active:
                    active = False; queued = None; q.append(None)                  # None = 묶음 끝
                wait = 1.0
            else:
                wait = 0.04
            continue
        wait = 0.02; gone = 0; active = True
        sm = small(img)
        if same(sm, queued):                                                        # 이미 줄에 넣은 화면 그대로
            prev = sm; moving = 0; continue
        if not same(sm, prev):                                                      # 아직 바뀌는 중 — 다음 캡처와 같아질 때까지 기다림 (0.4초 넘게 계속 바뀌면 그냥 넣음)
            prev = sm; moving = moving or time.time()
            if time.time() - moving < 0.4:
                continue
        moving = 0; prev = sm; queued = sm
        if len(q) < 60:
            q.append((img, (x, y, w, h)))
        St.gacha_wait = len(q)


def ocr_worker(q, game_rect):
    import capture
    St = GH.St; pend = None
    while not St.quit:
        if not q:
            time.sleep(0.03); continue
        item = q.popleft()
        if item is None:                                                            # 기록 화면을 닫음
            GH.chain = None; pend = None
            St.gacha_status = f'모은 기록 {count():,}건 — 관측 기록 화면을 열면 이어서 읽어요' if count() else ''
            continue
        img, (x, y, w, h) = item; tb, ub, k = boxes(w, h)
        scale = 2244 / img.width                                                   # OCR 은 표 너비 2244px(= 1280 기준의 3배)로 맞춰 읽음
        if abs(scale - 1) > 0.02:
            img = img.resize((2244, int(round(img.height * scale))))
        words = GH.ocr.read(img)
        if words is None:
            St.gacha_status = GH.ocr.err or '글자 인식을 쓰지 못했어요'; continue
        rows = parse(words, 3.0)
        if rows is None:
            dbg('NOT_TABLE', [w_[0] for w_ in words][:30], img); continue
        recs = to_records(rows) if rows else []
        if recs is None:                                                            # 넘기는 중간 화면이거나 잘못 읽힌 쪽 — 버림 (다시 지나가면 읽힘)
            GH.bad += 1; dbg('UNMATCHED', rows, img if GH.bad <= 20 else None)
            continue
        GH.bad = 0
        dbg('PAGE', rows, extra=f'q{len(q)}')
        if not rows:
            St.gacha_status = '이 관측 종류에는 기록이 없어요'; continue
        if not GH.data.get('uid') or GH.chain is None:                              # UID: 왼쪽 아래 글자 (처음 · 관측 종류를 새로 열 때 한 번)
            try:
                u = capture.grab((x + ub[0], y + ub[1], x + ub[2], y + ub[3])); u = u.resize((u.width * 2, u.height * 2)) if u.height < 130 else u
                m = re.search(r'[:：]\s*(\d{9,20})', ''.join(t for t, *_ in (GH.ocr.read(u) or [])))   # 'UID' 글자는 가끔 틀리게 읽혀서 ':' 뒤의 숫자만 봄
                if m and m.group(1) != GH.data.get('uid'):
                    if GH.data.get('uid') and count():                             # 다른 계정이면 기록을 섞지 않음 — 새 계정으로 다시 시작
                        os.replace(GH.path, GH.path.replace('.json', f'-{GH.data["uid"]}.json')) if os.path.exists(GH.path) else None
                        GH.data['types'] = {}
                    GH.data['uid'] = m.group(1)
            except Exception:
                pass
        feed(recs)
        if q:
            St.gacha_status += f' (읽을 화면 {len(q)}장 남음)'


def on_message(data):
    """사이트가 관측 기록을 달라고 하면 기존 트래커와 같은 형식으로 답함"""
    try:
        if json.loads(data).get('t') != 'gacha_get':
            return None
    except Exception:
        return None
    out = []; uid = GH.data.get('uid') or ''
    with GH.lock:
        for ty, rows in GH.data['types'].items():
            for at, grp in groups(rows):
                by = {}
                for r in chrono(grp):                                               # 그 분 안에서 관측한 순서대로 순번
                    key = at * 100000 + r['p']; s = by.get(key, 0); by[key] = s + 1
                    out.append({'r': key, 's': s, 'i': r['i'], 't': r['t'], 'n': 1, 'p': r['p'], 'at': at, 'g': int(ty), 'u': uid})
    out.sort(key=lambda x: (x['at'], x['r'], x['s']))
    return json.dumps({'t': 'gacha', 'v': 2, 'app': 'promilia-tracker', 'src': 'ocr', 'uid': uid, 'records': out}, ensure_ascii=False, separators=(',', ':'))


def start(St, here, game_rect):
    GH.St = St; GH.path = os.path.join(here, 'promilia-tracker2-gacha.json'); load()
    St.gacha_count = count(); St.gacha_status = ''

    def run():
        try:
            GH.names = Names(os.path.join(here, 'maps'))
        except Exception:
            St.gacha_status = '관측 자료를 받지 못했어요 (인터넷 연결 확인)'; return
        loop(game_rect)
    threading.Thread(target=run, daemon=True).start()
