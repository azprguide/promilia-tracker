"""새 버전 안내 (GitHub Releases) — 두 트래커 공용 (promilia-tracker2 · promilia-tracker 에 같은 파일)

GitHub 저장소의 릴리스 목록에서 '이 트래커의 채널' 태그 중 가장 높은 버전을 찾아, 지금 버전(VER)보다 높으면 화면에 알림만 함.
업데이트는 사용자가 「다운로드 페이지 열기」로 릴리스 페이지에서 직접 받음 — 트래커가 파일을 받거나 바꿔 끼우지 않음(강제 업데이트 없음).

- 채널(11-27): 두 트래커가 같은 저장소를 써도 서로의 릴리스를 새 버전으로 알리지 않게 태그 앞말로 나눔
    화면 인식 트래커(OCR) = 앞말 없음 (2.1.0 · v2.1.0) · 메모리 트래커 = 'mem-' (mem-1.2.0)
- 확인 주소: https://api.github.com/repos/<REPO>/releases?per_page=30 (로그인 · 토큰 없음 · 공개 저장소) · 임시 저장(draft) · 시험판(prerelease) 은 건너뜀
- 켤 때 한 번 조용히 확인(실패해도 알리지 않음) + 켜 둔 동안 6시간마다 다시 확인(새 릴리스를 올리면 실행 중인 트래커에도 안내가 뜸)
  고급 설정의 「업데이트 확인」으로 직접 확인 · 「켤 때 새 버전 확인」을 끄면 자동 확인을 하지 않음
"""
import json, re, ssl, threading, time, urllib.request

RECHECK_SEC = 6 * 3600


def vtuple(v):
    n = [int(x) for x in re.findall(r'\d+', str(v))[:4]]
    return tuple(n + [0] * (4 - len(n)))


class Updater:
    def __init__(self, St, repo, ver, app, prefix='', api='https://api.github.com', auto=None):
        self.St, self.repo, self.ver, self.app, self.api = St, repo.strip().strip('/'), ver, app, api.rstrip('/')
        self.prefix = prefix                      # 채널 태그 앞말 ('' = OCR · 'mem-' = 메모리)
        self.auto = auto or (lambda: True)        # 자동 확인을 할지 (설정 'autoupdate')
        # state: '' 확인 전 · check 확인 중 · none 최신 · avail 새 버전 있음 · error
        St.upd = {'state': '', 'ver': '', 'notes': '', 'msg': '', 'page': '', 'hide': False, 'at': 0.0}
        self.busy = False

    def _set(self, **kw):
        self.St.upd.update(kw)

    def repo_page(self):
        return f'https://github.com/{self.repo}' if self.repo else ''

    def page(self):
        return self.St.upd.get('page') or (f'https://github.com/{self.repo}/releases' if self.repo else '')

    def tag_ver(self, tag):
        """이 채널의 태그면 버전 문자열, 아니면 None"""
        t = str(tag or '').strip()
        if self.prefix:
            if not t.lower().startswith(self.prefix.lower()):
                return None
            t = t[len(self.prefix):]
        elif not re.match(r'^[vV]?\d', t):      # OCR 채널: 숫자(또는 v+숫자)로 시작하는 태그만 — mem-… 등 다른 채널 제외
            return None
        t = t.lstrip('vV')
        return t if re.match(r'^\d+(\.\d+)*', t) else None

    def start_auto(self):
        """켤 때 한 번 + 6시간마다 (켜 둔 동안) — 자동 확인이 꺼져 있으면 건너뜀"""
        def loop():
            first = True
            while not getattr(self.St, 'quit', False):
                if self.auto():
                    self.check(quiet=True)
                for _ in range(int((5 if first else RECHECK_SEC) // 5)):
                    if getattr(self.St, 'quit', False):
                        return
                    time.sleep(5)
                first = False
        threading.Thread(target=loop, daemon=True).start()

    def check(self, quiet=False):
        if self.busy or not self.repo or '/' not in self.repo:
            if not quiet and not self.repo:
                self._set(state='error', msg='업데이트 저장소가 정해지지 않았어요')
            return
        self.busy = True
        threading.Thread(target=self._check, args=(quiet,), daemon=True).start()

    def _check(self, quiet):
        try:
            if not quiet or self.St.upd.get('state') != 'avail':
                self._set(state='check', msg='업데이트 확인 중…')
            req = urllib.request.Request(f'{self.api}/repos/{self.repo}/releases?per_page=30',
                                         headers={'User-Agent': f'PromiliaTracker/{self.ver}', 'Accept': 'application/vnd.github+json'})
            with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
                rels = json.load(r)
            best = None
            for rel in rels if isinstance(rels, list) else []:
                if rel.get('draft') or rel.get('prerelease'):
                    continue
                v = self.tag_ver(rel.get('tag_name'))
                if v and (best is None or vtuple(v) > vtuple(best[0])):
                    best = (v, rel)
            self._set(at=time.time())
            if not best or vtuple(best[0]) <= vtuple(self.ver):
                self._set(state='none', ver=best[0] if best else '', msg=f'최신 버전이에요 (v{self.ver})')
                return
            tag, rel = best
            was = self.St.upd.get('state') == 'avail' and self.St.upd.get('ver') == tag
            notes = re.sub(r'\r\n?', '\n', rel.get('body') or '').strip()
            # 본문 첫 줄 중 제목(#) · 빈 줄이 아닌 것 → 안내 카드의 한 줄 요약
            line = next((re.sub(r'^[-*•\s]+', '', l).replace('**', '').strip() for l in notes.split('\n') if l.strip() and not l.lstrip().startswith('#')), '')
            self._set(state='avail', ver=tag, notes=line[:200], hide=self.St.upd.get('hide') if was else False,
                      page=rel.get('html_url') or f'https://github.com/{self.repo}/releases',
                      msg=f'새 버전 v{tag} 이 나왔어요')
        except Exception as e:
            if quiet:
                if self.St.upd.get('state') == 'check':
                    self._set(state='', msg='')
            else:
                self._set(state='error', msg=f'업데이트를 확인하지 못했어요 ({type(e).__name__})')
        finally:
            self.busy = False
