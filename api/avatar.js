// Resolve a handle to its avatar, then proxy the bytes. Going direct to
// pbs.twimg.com from the page needs a no-referrer policy and still fails in
// some browsers; serving it from our own origin never does.
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/126.0 Safari/537.36';

const clean = (h = '') => String(h).trim().replace(/^@/, '').replace(/[^A-Za-z0-9_]/g, '').slice(0, 15);

export default async function handler(req, res) {
  const h = clean(req.query?.h);
  if (!h) return res.status(400).end();
  try {
    const meta = await fetch(`https://api.fxtwitter.com/${h}`, {
      headers: { 'user-agent': UA, accept: 'application/json' },
    }).then((r) => (r.ok ? r.json() : null));

    const url = meta?.user?.avatar_url;
    if (!url) return res.status(404).end();

    const img = await fetch(url.replace('_normal', '_400x400'), { headers: { 'user-agent': UA } });
    if (!img.ok) return res.status(502).end();

    const buf = Buffer.from(await img.arrayBuffer());
    res.setHeader('content-type', img.headers.get('content-type') || 'image/jpeg');
    res.setHeader('cache-control', 's-maxage=86400, stale-while-revalidate=604800');
    return res.status(200).send(buf);
  } catch {
    return res.status(502).end();
  }
}
