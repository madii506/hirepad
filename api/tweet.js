// A post's view count — the only number POT actually settles on.
// FxTwitter is the one source that reports views; syndication is the fallback
// and does NOT carry views, so the page must show a dash rather than a zero.
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/126.0 Safari/537.36';

function idFrom(input = '') {
  const s = String(input).trim();
  const m = s.match(/status(?:es)?\/(\d{1,25})/) || s.match(/^(\d{1,25})$/);
  return m ? m[1] : null;
}

function synToken(id) {
  return ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, '');
}

async function grab(url, ms = 6000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, headers: { 'user-agent': UA, accept: 'application/json' } });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; } finally { clearTimeout(t); }
}

export default async function handler(req, res) {
  const id = idFrom(req.query?.id || req.query?.url);
  res.setHeader('cache-control', 's-maxage=120, stale-while-revalidate=600');
  if (!id) return res.status(400).json({ error: 'post id or url required' });

  const fx = await grab(`https://api.fxtwitter.com/i/status/${id}`);
  const t = fx?.tweet;
  if (t) {
    return res.status(200).json({
      id,
      views: typeof t.views === 'number' ? t.views : null,
      likes: t.likes ?? null,
      reposts: t.retweets ?? null,
      replies: t.replies ?? null,
      text: t.text ?? null,
      created: t.created_at ?? null,
      handle: t.author?.screen_name ?? null,
      name: t.author?.name ?? null,
      avatar: t.author?.avatar_url ?? null,
      url: t.url ?? `https://x.com/i/status/${id}`,
      exists: true,
      src: 'fxtwitter',
    });
  }

  const syn = await grab(`https://cdn.syndication.twimg.com/tweet-result?id=${id}&token=${synToken(id)}&lang=en`);
  if (syn) {
    return res.status(200).json({
      id,
      views: null,                    // syndication never reports views
      likes: syn.favorite_count ?? null,
      reposts: syn.conversation_count ?? null,
      replies: null,
      text: syn.text ?? null,
      created: syn.created_at ?? null,
      handle: syn.user?.screen_name ?? null,
      name: syn.user?.name ?? null,
      avatar: syn.user?.profile_image_url_https ?? null,
      url: `https://x.com/i/status/${id}`,
      exists: true,
      src: 'syndication',
    });
  }

  return res.status(200).json({ id, views: null, exists: false, src: 'none' });
}
