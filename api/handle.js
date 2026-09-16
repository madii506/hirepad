// Resolve an X handle. FxTwitter first, syndication as the fallback.
// Returns a stable shape so the page never has to branch on the source.
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/126.0 Safari/537.36';

const clean = (h = '') => String(h).trim().replace(/^@/, '').replace(/[^A-Za-z0-9_]/g, '').slice(0, 15);

async function grab(url, ms = 5000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, headers: { 'user-agent': UA, accept: 'application/json' } });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; } finally { clearTimeout(t); }
}

export default async function handler(req, res) {
  const h = clean(req.query?.h);
  res.setHeader('cache-control', 's-maxage=300, stale-while-revalidate=600');
  if (!h) return res.status(400).json({ error: 'handle required' });

  const fx = await grab(`https://api.fxtwitter.com/${h}`);
  const u = fx?.user;
  if (u) {
    return res.status(200).json({
      handle: u.screen_name || h,
      name: u.name || null,
      followers: typeof u.followers === 'number' ? u.followers : null,
      verified: !!u.verified,
      avatar: u.avatar_url || null,
      exists: true,
      src: 'fxtwitter',
    });
  }

  const syn = await grab(`https://cdn.syndication.twimg.com/timeline/profile?screen_name=${h}`);
  if (syn) {
    return res.status(200).json({
      handle: h, name: null, followers: null, verified: false,
      avatar: null, exists: true, src: 'syndication',
    });
  }

  return res.status(200).json({
    handle: h, name: null, followers: null, verified: false,
    avatar: null, exists: false, src: 'none',
  });
}
