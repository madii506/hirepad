// Market read for the mint. pump.fun lives on Solana, so this is Dexscreener
// filtered to chainId 'solana' — there is no Blockscout here and no 0x address.
// The creator fee is set at launch and is configurable, so the pot is derived
// from whatever rate is actually passed in rather than a hardcoded guess.
const DS = 'https://api.dexscreener.com/latest/dex/tokens/';

// Solana mints are base58, 32–44 chars. No 0/O/I/l in the alphabet.
const isMint = (s = '') => /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(String(s).trim());

async function grab(url, ms = 6000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, headers: { accept: 'application/json' } });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; } finally { clearTimeout(t); }
}

export default async function handler(req, res) {
  const ca = String(req.query?.ca || '').trim();
  // creator fee as a percent, e.g. 1 means 1.00%. pump.fun caps it at 3.00%.
  const feePct = Math.min(3, Math.max(0, Number(req.query?.fee ?? 1)));
  res.setHeader('cache-control', 's-maxage=45, stale-while-revalidate=180');
  if (!isMint(ca)) return res.status(400).json({ error: 'solana mint address required' });

  const ds = await grab(DS + ca);
  const pairs = (ds?.pairs || []).filter((p) => p.chainId === 'solana');
  pairs.sort((a, b) => (b.liquidity?.usd || 0) - (a.liquidity?.usd || 0));
  const p = pairs[0] || null;

  const vol24 = p?.volume?.h24 ?? null;
  const feePerDay = vol24 == null ? null : vol24 * (feePct / 100);

  return res.status(200).json({
    ca,
    chain: 'solana',
    venue: 'pump.fun',
    feePct,
    hasPair: !!p,
    price: p?.priceUsd ? Number(p.priceUsd) : null,
    marketCap: p?.marketCap ?? p?.fdv ?? null,
    liquidity: p?.liquidity?.usd ?? null,
    volume24: vol24,
    change24: p?.priceChange?.h24 ?? null,
    pairUrl: p?.url ?? null,
    feePerDay,
    feePerHour: feePerDay == null ? null : feePerDay / 24,
    name: p?.baseToken?.name ?? null,
    symbol: p?.baseToken?.symbol ?? null,
  });
}
