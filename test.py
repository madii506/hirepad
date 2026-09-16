import asyncio, hashlib, re, sys
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8833'
ARGS = ['--no-sandbox', '--use-gl=swiftshader', '--disable-dev-shm-usage']

JOB = 'Read every reply to the pinned post and summarise the questions.'


async def main():
    bad = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=ARGS)

        # ══════════════════ index.html ══════════════════
        for w, h, label in ((1400, 900, 'desktop'), (390, 844, 'phone')):
            pg = await b.new_page(viewport={'width': w, 'height': h})
            errs = []
            pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
            await pg.goto(BASE + '/', wait_until='domcontentloaded')
            await pg.wait_for_timeout(2400)

            # scrollWidth is clamped by overflow-x:hidden, so it can look clean
            # while content is being clipped. Measure the elements themselves.
            over = await pg.evaluate('''(vw)=>{
                const scrolls = e => {
                  for (let p=e.parentElement; p; p=p.parentElement){
                    const ox = getComputedStyle(p).overflowX;
                    if (ox === 'auto' || ox === 'scroll') return true;
                  }
                  return false;
                };
                return [...document.querySelectorAll('body *')]
                  .filter(e=>{const r=e.getBoundingClientRect();
                              return r.width>0 && (r.right>vw+2 || r.left<-2) && !scrolls(e);})
                  .slice(0,6)
                  .map(e=>e.tagName+'.'+e.className+' @'+Math.round(e.getBoundingClientRect().right));
              }''', w)
            if over:
                bad.append(f'{label}: content outside the viewport :: {over}')

            # the seal must have computed itself into characters
            seal = await pg.inner_text('#seal')
            if len(seal.strip()) < 120:
                bad.append(f'{label}: ascii seal did not render ({len(seal.strip())} chars)')
            if seal.strip() == '[H]':
                bad.append(f'{label}: ascii seal fell back')

            # ── NOTHING IS PRE-FILLED. We are not live. ──────────────────
            for sel in ('#f-job', '#f-price', '#f-deadline', '#f-bal', '#f-ask', '#f-url', '#f-h'):
                v = await pg.input_value(sel)
                if v.strip():
                    bad.append(f'{label}: {sel} ships pre-filled with {v!r} — nothing is live yet')
            if 'enter a job' not in (await pg.inner_text('#A-canon')).lower():
                bad.append(f'{label}: Schedule A should start empty')
            if 'enter a balance' not in (await pg.inner_text('#B-bar')).lower():
                bad.append(f'{label}: Schedule B should start empty')
            for sel in ('#B-ceil', '#B-can', '#B-win', '#B-lose', '#B-ruin',
                        '#A-hc', '#A-hs', '#A-match', '#A-amt', '#A-fail'):
                if (await pg.inner_text(sel)).strip() != '—':
                    bad.append(f'{label}: {sel} shows a figure before anything was entered')

            # the old dashboard template must be gone
            txt = (await pg.inner_text('body')).lower()
            for phrase in ('jobs delivered', 'bonds forfeited', 'claims required',
                           'no jobs have been taken yet', '0 jobs', 'paid out total'):
                if phrase in txt:
                    bad.append(f'{label}: invented dashboard figure survives -> {phrase!r}')
            # word-bounded: 'pons' is a substring of 'response'
            for stale in (r'robinhood', r'\bpons\b', r'\$pot\b', r'\blorem\b'):
                if re.search(stale, txt):
                    bad.append(f'{label}: stale reference {stale!r}')
            if 'scamming you' not in txt:
                bad.append(f'{label}: scam warning missing')

            if label == 'phone':
                await pg.click('#rb'); await pg.wait_for_timeout(250)
                if not await pg.is_visible('#idx a'):
                    bad.append('phone: contents did not open')
                await pg.screenshot(path='/tmp/hire-phone.png', full_page=True)
                errs = [e for e in errs if 'favicon' not in e.lower() and 'fonts.g' not in e
                        and 'ERR_' not in e and '404' not in e]
                if errs:
                    bad.append(f'{label} console: ' + ' | '.join(errs[:5]))
                await pg.close()
                continue

            # ── black and white only ─────────────────────────────────────
            bg = await pg.evaluate("getComputedStyle(document.body).backgroundColor")
            if bg not in ('rgb(0, 0, 0)',):
                bad.append(f'background is not black: {bg}')
            tinted = await pg.evaluate('''[...document.querySelectorAll('*')].map(e=>{
                const s=getComputedStyle(e);
                for (const p of ['color','backgroundColor','borderTopColor','borderLeftColor']){
                  const m=s[p].match(/rgba?\\((\\d+), (\\d+), (\\d+)/);
                  if(!m) continue;
                  const [r,g,b]=[+m[1],+m[2],+m[3]];
                  if(Math.max(r,g,b)-Math.min(r,g,b) > 26) return e.tagName+'.'+e.className+' '+p+' '+s[p];
                }
                return null;
              }).filter(Boolean).slice(0,5)''')
            if tinted:
                bad.append(f'non-greyscale colour found: {tinted}')

            # ── clause structure, not the old band template ──────────────
            nos = await pg.eval_on_selector_all('.cl > .ch > .no', 'e=>e.map(x=>x.textContent.trim())')
            want = ['§' + str(i) for i in range(1, 13)]
            if nos != want:
                bad.append(f'clause numbering is {nos}')
            idx = await pg.eval_on_selector_all('#idx a', 'e=>e.length')
            if idx != 12:
                bad.append(f'contents lists {idx} clauses, expected 12')
            if await pg.evaluate("getComputedStyle(document.querySelector('.rail')).position") != 'sticky':
                bad.append('the rail is not sticky on desktop')

            # ── Schedule A: real crypto, cross-checked ───────────────────
            await pg.fill('#f-job', JOB)
            await pg.fill('#f-price', '40')
            await pg.fill('#f-deadline', '24')
            await pg.wait_for_timeout(1800)
            hc = (await pg.inner_text('#A-hc')).strip()
            hs = (await pg.inner_text('#A-hs')).strip()
            if not (len(hc) == 64 and all(c in '0123456789abcdef' for c in hc)):
                bad.append(f'browser sha-256 is not a hex digest: {hc[:70]!r}')
            if hc != hs:
                bad.append(f'client/server hash disagree: {hc[:20]} vs {hs[:20]}')
            if (await pg.inner_text('#A-ts')).strip().lower() != 'match':
                bad.append('Schedule A: server tag is not "match"')
            if 'identical' not in (await pg.inner_text('#A-match')).lower():
                bad.append('Schedule A: agreement line does not confirm')
            canon = await pg.inner_text('#A-canon')
            want_h = hashlib.sha256(canon.encode('utf-8')).hexdigest()
            if want_h != hc:
                bad.append(f'the shown canonical string does not hash to the shown digest '
                           f'({want_h[:14]} vs {hc[:14]})')
            if (await pg.input_value('#f-bond')).strip() != '$40.00':
                bad.append('Schedule A: bond should mirror the price')
            if '$80.00' not in await pg.inner_text('#A-fail'):
                bad.append('Schedule A: failure payout should be twice the price')

            before = hc
            await pg.click('#b-tamper'); await pg.wait_for_timeout(1600)
            if (await pg.inner_text('#A-hc')).strip() == before:
                bad.append('tamper: one character did not move the hash')
            if (await pg.inner_text('#A-ts')).strip().lower() != 'match':
                bad.append('tamper: server did not re-agree')

            await pg.click('#b-clear'); await pg.wait_for_timeout(400)
            if 'enter a job' not in (await pg.inner_text('#A-canon')).lower():
                bad.append('clear did not reset Schedule A')

            # ── Schedule B: exact arithmetic, and empty until asked ──────
            await pg.fill('#f-bal', '2500'); await pg.fill('#f-ask', '400')
            await pg.wait_for_timeout(250)
            for sel, exp in (('#B-ceil', '$2,500.00'), ('#B-win', '$2,900.00'),
                             ('#B-lose', '$2,100.00'), ('#B-ruin', '6')):
                got = (await pg.inner_text(sel)).strip()
                if got != exp:
                    bad.append(f'capacity {sel}: got {got!r} expected {exp!r}')
            await pg.fill('#f-ask', '4000'); await pg.wait_for_timeout(250)
            can = (await pg.inner_text('#B-can')).lower()
            if 'no' not in can or '1,500.00' not in can:
                bad.append(f'capacity: over-ceiling job should be refused with the gap -> {can!r}')
            if (await pg.inner_text('#B-win')).strip() != '—':
                bad.append('capacity: a refused job must not show an outcome balance')
            await pg.fill('#f-bal', ''); await pg.wait_for_timeout(250)
            if 'enter a balance' not in (await pg.inner_text('#B-bar')).lower():
                bad.append('capacity: clearing the balance should return to empty')

            # ── Schedule C readers ───────────────────────────────────────
            await pg.fill('#f-url', 'not a url')
            await pg.click('#b-read'); await pg.wait_for_timeout(900)
            if 'does not look like' not in await pg.inner_text('#o-read'):
                bad.append('reader: bad input not rejected client-side')
            await pg.fill('#f-url', 'https://x.com/cobie/status/1519480761749016577')
            await pg.click('#b-read'); await pg.wait_for_timeout(6000)
            if 'reading…' in await pg.inner_text('#o-read'):
                bad.append('reader: post read never resolved')
            await pg.fill('#f-h', 'elonmusk')
            await pg.click('#b-handle'); await pg.wait_for_timeout(6000)
            if 'reading…' in await pg.inner_text('#o-handle'):
                bad.append('reader: handle read never resolved')

            # ── probes ───────────────────────────────────────────────────
            await pg.click('#b-probe'); await pg.wait_for_timeout(9000)
            stuck = await pg.eval_on_selector_all(
                '#probe .st', 'e=>e.filter(x=>x.className.includes("wait")).length')
            if stuck:
                bad.append(f'{stuck} probes never resolved')
            if 'responding' not in await pg.inner_text('#probe tr[data-p="bond"] .st'):
                bad.append('the bond endpoint probe is not green')

            # ── links and anchors ────────────────────────────────────────
            r = await pg.request.get(BASE + '/docs.html')
            if r.status != 200:
                bad.append(f'docs.html returns {r.status}')
            if not await pg.query_selector('a[href="docs.html"]'):
                bad.append('no link to the reference')
            hrefs = await pg.eval_on_selector_all('a[href^="#"]', 'e=>e.map(x=>x.getAttribute("href"))')
            for hh in set(hrefs):
                if hh != '#' and not await pg.query_selector(hh):
                    bad.append(f'dead anchor {hh}')

            broken = await pg.evaluate('''[...document.images]
                .filter(i=>i.complete && i.naturalWidth===0 && i.getAttribute('src'))
                .map(i=>i.getAttribute('src'))''')
            if broken:
                bad.append('broken images: ' + str(broken))

            await pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await pg.wait_for_timeout(1500)
            inv = await pg.evaluate('''[...document.querySelectorAll('.rv')]
                .filter(e=>getComputedStyle(e).opacity!=='1').length''')
            if inv:
                bad.append(f'{inv} clauses still transparent')

            await pg.screenshot(path='/tmp/hire-desktop.png', full_page=True)
            errs = [e for e in errs if 'favicon' not in e.lower() and 'fonts.g' not in e
                    and 'ERR_' not in e and '404' not in e]
            if errs:
                bad.append(f'{label} console: ' + ' | '.join(errs[:5]))
            await pg.close()

        # ══════════════════ docs.html ══════════════════
        for w, h, label in ((1400, 900, 'docs'), (390, 844, 'docs-phone')):
            pg = await b.new_page(viewport={'width': w, 'height': h})
            errs = []
            pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
            pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
            await pg.goto(BASE + '/docs.html', wait_until='domcontentloaded')
            await pg.wait_for_timeout(1500)

            sw = await pg.evaluate('document.documentElement.scrollWidth')
            if sw > w + 2:
                bad.append(f'{label}: scrollWidth {sw} > {w}')

            if label == 'docs':
                links = await pg.eval_on_selector_all('#toc a', 'e=>e.length')
                if links < 8:
                    bad.append(f'docs: rail built only {links} links')
                hrefs = await pg.eval_on_selector_all('a[href^="#"]', 'e=>e.map(x=>x.getAttribute("href"))')
                for hh in set(hrefs):
                    if hh != '#' and not await pg.query_selector(hh):
                        bad.append(f'docs: dead anchor {hh}')
                btns = await pg.query_selector_all('[data-try]')
                if len(btns) < 4:
                    bad.append(f'docs: only {len(btns)} try buttons')
                await btns[0].click(); await pg.wait_for_timeout(5000)
                res = await pg.inner_text('.ep .res')
                if 'calling' in res or not res.strip():
                    bad.append(f'docs: try-it never resolved :: {res[:90]!r}')
                d = (await pg.inner_text('body')).lower()
                if 'scamming you' not in d:
                    bad.append('docs: scam warning missing')
                for stale in (r'robinhood', r'\bpons\b', r'\$pot\b'):
                    if re.search(stale, d):
                        bad.append(f'docs: stale reference {stale!r}')
                await pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await pg.wait_for_timeout(1400)
                inv = await pg.evaluate('''[...document.querySelectorAll('.rv')]
                    .filter(e=>getComputedStyle(e).opacity!=='1').length''')
                if inv:
                    bad.append(f'docs: {inv} sections still transparent')
                await pg.screenshot(path='/tmp/hire-docs.png', full_page=True)
            else:
                await pg.click('#mb'); await pg.wait_for_timeout(250)
                if not await pg.is_visible('#menu a'):
                    bad.append('docs-phone: menu did not open')

            errs = [e for e in errs if 'favicon' not in e.lower() and 'fonts.g' not in e
                    and 'ERR_' not in e and '404' not in e]
            if errs:
                bad.append(f'{label} console: ' + ' | '.join(errs[:5]))
            await pg.close()

        await b.close()

    print('FAILURES:' if bad else 'ALL CHECKS PASSED')
    for x in bad:
        print(' -', x)
    sys.exit(1 if bad else 0)

asyncio.run(main())
