import asyncio, hashlib, sys
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8833'
ARGS = ['--no-sandbox', '--use-gl=swiftshader', '--disable-dev-shm-usage']


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
            await pg.wait_for_timeout(2500)

            sw = await pg.evaluate('document.documentElement.scrollWidth')
            if sw > w + 2:
                over = await pg.evaluate('''(vw)=>[...document.querySelectorAll('*')]
                    .filter(e=>e.getBoundingClientRect().right>vw+2)
                    .slice(0,6).map(e=>e.tagName+'.'+e.className)''', w)
                bad.append(f'{label}: scrollWidth {sw} > {w} :: {over}')

            # the hero must actually have computed itself
            art = await pg.inner_text('#art')
            if 'computing' in art:
                bad.append(f'{label}: ascii hero never rendered')
            elif len(art.strip()) < 200:
                bad.append(f'{label}: ascii hero suspiciously small ({len(art)} chars)')
            elif art.strip() == 'HIRE':
                bad.append(f'{label}: ascii hero fell back to plain text')

            if label != 'desktop':
                await pg.click('#mb'); await pg.wait_for_timeout(250)
                if not await pg.is_visible('#menu a'):
                    bad.append('phone: menu did not open')
                await pg.screenshot(path='/tmp/hire-phone.png', full_page=True)
                errs = [e for e in errs if 'favicon' not in e.lower() and 'fonts.g' not in e
                        and 'ERR_' not in e and '404' not in e]
                if errs:
                    bad.append(f'{label} console: ' + ' | '.join(errs[:5]))
                await pg.close()
                continue

            # ── the flicker must not be on <body> (kills position:sticky) ──
            if await pg.evaluate("getComputedStyle(document.body).animationName") != 'none':
                bad.append('flicker is on <body> — that breaks position:sticky')
            if await pg.evaluate("getComputedStyle(document.querySelector('nav')).position") != 'sticky':
                bad.append('nav lost its sticky positioning')
            if not await pg.query_selector('.crt'):
                bad.append('flicker overlay missing')

            # ── 02 the bond: the whole point is the two hashes agree ──────
            await pg.wait_for_timeout(1500)
            hc = (await pg.inner_text('#o-hash-c')).strip()
            hs = (await pg.inner_text('#o-hash-s')).strip()
            if not (len(hc) == 64 and all(c in '0123456789abcdef' for c in hc)):
                bad.append(f'browser sha-256 is not a hex digest: {hc[:80]!r}')
            if hc != hs:
                bad.append(f'client/server hash disagree: {hc[:24]} vs {hs[:24]}')
            if 'identical' not in (await pg.inner_text('#o-match')).lower():
                bad.append('bond: match line does not confirm agreement -> '
                           + (await pg.inner_text('#o-match'))[:90])
            if (await pg.inner_text('#bdg-server')).strip().lower() != 'match':
                bad.append('bond: server badge is not "match"')

            # and the hash must be the real sha-256 of the shown canonical string
            canon = await pg.inner_text('#o-canon')
            want = hashlib.sha256(canon.encode('utf-8')).hexdigest()
            if want != hc:
                bad.append(f'the published canonical string does not hash to the shown digest '
                           f'({want[:16]} vs {hc[:16]})')

            # the layout table filled in from the server
            rows = await pg.eval_on_selector_all('#o-layout tr', 'e=>e.length')
            if rows < 5:
                bad.append(f'bond: byte layout only rendered {rows} rows')

            # ── tamper must move the hash ─────────────────────────────────
            before = hc
            await pg.click('#b-tamper'); await pg.wait_for_timeout(1400)
            after = (await pg.inner_text('#o-hash-c')).strip()
            if after == before:
                bad.append('tamper: one-character change did not move the hash')
            if (await pg.inner_text('#bdg-server')).strip().lower() != 'match':
                bad.append('tamper: server did not re-agree after the edit')

            # empty job must degrade honestly, not throw
            await pg.fill('#f-job', '')
            await pg.wait_for_timeout(900)
            if 'required' not in (await pg.inner_text('#o-canon')).lower():
                bad.append('bond: empty job should say a job is required')
            await pg.fill('#f-job', 'Collect the receipts and post them in this thread.')
            await pg.wait_for_timeout(1400)

            # ── 03 the ceiling: exact arithmetic ──────────────────────────
            await pg.fill('#f-bal', '2500'); await pg.fill('#f-ask', '400')
            await pg.wait_for_timeout(200)
            checks = {'#c-ceil': '$2,500.00', '#c-win': '$2,900.00',
                      '#c-lose': '$2,100.00', '#c-ruin': '6'}
            for sel, exp in checks.items():
                got = (await pg.inner_text(sel)).strip()
                if got != exp:
                    bad.append(f'ceiling {sel}: got {got!r} expected {exp!r}')
            if 'yes' not in (await pg.inner_text('#c-can')).lower():
                bad.append('ceiling: 400 <= 2500 should be acceptable')

            await pg.fill('#f-ask', '4000'); await pg.wait_for_timeout(200)
            can = (await pg.inner_text('#c-can')).lower()
            if 'no' not in can or '1,500.00' not in can:
                bad.append(f'ceiling: over-ceiling job should be refused and show the gap -> {can!r}')
            if (await pg.inner_text('#c-win')).strip() != '—':
                bad.append('ceiling: a refused job must not show an outcome balance')

            await pg.fill('#f-bal', '0'); await pg.fill('#f-ask', '100')
            await pg.wait_for_timeout(200)
            if (await pg.inner_text('#c-ceil')).strip() != '$0.00':
                bad.append('ceiling: empty wallet should read $0.00')
            await pg.fill('#f-bal', '2500'); await pg.fill('#f-ask', '400')
            await pg.wait_for_timeout(200)

            # ── 04 readers ────────────────────────────────────────────────
            await pg.fill('#f-url', 'not a url')
            await pg.click('#b-read'); await pg.wait_for_timeout(1200)
            if 'does not look like' not in await pg.inner_text('#o-read'):
                bad.append('reader: bad input was not rejected client-side')
            await pg.fill('#f-url', 'https://x.com/cobie/status/1519480761749016577')
            await pg.click('#b-read'); await pg.wait_for_timeout(6000)
            o = await pg.inner_text('#o-read')
            if 'Reading from X' in o:
                bad.append('reader: post read never resolved')
            await pg.click('#b-rclear'); await pg.wait_for_timeout(200)
            if not await pg.is_hidden('#o-read'):
                bad.append('reader: clear did not hide the output')

            await pg.fill('#f-h', '@@bad@@')
            await pg.click('#b-handle'); await pg.wait_for_timeout(800)
            if 'not a valid' not in await pg.inner_text('#o-handle'):
                bad.append('reader: invalid handle was not rejected client-side')
            await pg.fill('#f-h', 'elonmusk')
            await pg.click('#b-handle'); await pg.wait_for_timeout(6000)
            if 'Reading from X' in await pg.inner_text('#o-handle'):
                bad.append('reader: handle read never resolved')

            # ── 08 probes all resolve ─────────────────────────────────────
            await pg.click('#b-probe'); await pg.wait_for_timeout(9000)
            stuck = await pg.eval_on_selector_all(
                '#probe-body .st', 'e=>e.filter(x=>x.className.includes("wait")).length')
            if stuck:
                bad.append(f'{stuck} probes never resolved')
            nprobe = await pg.eval_on_selector_all('#probe-body tr', 'e=>e.length')
            if nprobe != 5:
                bad.append(f'expected 5 probe rows, found {nprobe}')
            # /api/bond is ours and must be green regardless of the network
            bondst = await pg.inner_text('#probe-body tr[data-p="bond"] .st')
            if 'responding' not in bondst:
                bad.append(f'the bond endpoint probe is not green: {bondst!r}')

            # ── structure ─────────────────────────────────────────────────
            for sec in ('#rule', '#bond', '#ceiling', '#read', '#ledger',
                        '#limits', '#spec', '#status', '#faq'):
                if not await pg.query_selector(sec):
                    bad.append(f'section {sec} missing')
            nums = await pg.eval_on_selector_all(
                'section .eyebrow b', 'e=>e.map(x=>x.textContent.trim())')
            if nums != ['0' + str(i) for i in range(1, 10)]:
                bad.append(f'section numbering is {nums}')

            if not await pg.query_selector('nav a[href="docs.html"]'):
                bad.append('no docs link in the nav')
            r = await pg.request.get(BASE + '/docs.html')
            if r.status != 200:
                bad.append(f'docs.html returns {r.status}')

            hrefs = await pg.eval_on_selector_all('a[href^="#"]', 'e=>e.map(x=>x.getAttribute("href"))')
            for hh in set(hrefs):
                if hh != '#' and not await pg.query_selector(hh):
                    bad.append(f'dead anchor {hh}')

            body = (await pg.inner_text('body')).lower()
            for stale in ('robinhood', 'pons', '$pot', 'lorem'):
                if stale in body:
                    bad.append(f'stale reference {stale!r}')
            if 'scamming you' not in body:
                bad.append('scam warning missing')
            for must in ('x money', 'sha-256', 'pump.fun' if 'pump.fun' in body else 'x money'):
                if must not in body:
                    bad.append(f'page never mentions {must!r}')

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
                bad.append(f'{inv} .rv sections still transparent')

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
                over = await pg.evaluate('''(vw)=>[...document.querySelectorAll('*')]
                    .filter(e=>e.getBoundingClientRect().right>vw+2)
                    .slice(0,6).map(e=>e.tagName+'.'+e.className)''', w)
                bad.append(f'{label}: scrollWidth {sw} > {w} :: {over}')

            if label == 'docs':
                links = await pg.eval_on_selector_all('#toc a', 'e=>e.length')
                if links < 8:
                    bad.append(f'docs: on-this-page rail built only {links} links')
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
                    bad.append(f'docs: try-it never resolved :: {res[:100]!r}')
                d = (await pg.inner_text('body')).lower()
                if 'scamming you' not in d:
                    bad.append('docs: scam warning missing')
                for stale in ('robinhood', 'pons', '$pot'):
                    if stale in d:
                        bad.append(f'docs: stale reference {stale!r}')
                await pg.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await pg.wait_for_timeout(1400)
                inv = await pg.evaluate('''[...document.querySelectorAll('.rv')]
                    .filter(e=>getComputedStyle(e).opacity!=='1').length''')
                if inv:
                    bad.append(f'docs: {inv} .rv sections still transparent')
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
