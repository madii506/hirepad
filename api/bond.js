// The bond commitment. HIRE hashes the exact job terms before it starts work,
// and that hash is what goes onchain. This computes it server-side so the page
// can check its own Web Crypto result against an independent implementation —
// if the two ever disagree, one of them is wrong and you can see it.
//
// The canonical form is byte-exact and is the whole point: change one character
// of the job text and the hash changes, so the terms cannot be rewritten after
// somebody has paid.
import { createHash } from 'node:crypto';

const MAX_JOB = 2000;

/** Collapse to a single deterministic line so whitespace can't shift the hash. */
export const normalise = (s = '') =>
  String(s).replace(/\s+/g, ' ').trim().slice(0, MAX_JOB);

export function canonical({ job, price, bond, deadline }) {
  return [
    'HIRE/v1',
    `job=${normalise(job)}`,
    `price=${price}`,
    `bond=${bond}`,
    `deadline=${deadline}h`,
  ].join('\n');
}

const int = (v, dflt, lo, hi) => {
  const n = Math.floor(Number(v));
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt;
};

export default async function handler(req, res) {
  const job = normalise(req.query?.job);
  if (!job) return res.status(400).json({ error: 'job text required' });

  // Everything in whole cents — no floats anywhere near the commitment.
  const price = int(req.query?.price, 0, 0, 100_000_000);
  // The bond equals the price: failing costs it exactly what delivering pays.
  const bond = price;
  const deadline = int(req.query?.deadline, 24, 1, 720);

  const msg = canonical({ job, price, bond, deadline });
  const hash = createHash('sha256').update(msg, 'utf8').digest('hex');

  return res.status(200).json({
    ok: true,
    job,
    jobChars: job.length,
    price,
    bond,
    deadline,
    canonical: msg,
    canonicalBytes: Buffer.byteLength(msg, 'utf8'),
    hash,
    // what the onchain account would carry, in the order it carries it
    layout: [
      { field: 'discriminator', bytes: 8, value: 'open_bond' },
      { field: 'agent', bytes: 32, value: 'the agent pubkey' },
      { field: 'job_hash', bytes: 32, value: hash },
      { field: 'price_cents', bytes: 8, value: String(price) },
      { field: 'bond_cents', bytes: 8, value: String(bond) },
      { field: 'deadline_slot', bytes: 8, value: `+${deadline}h` },
      { field: 'state', bytes: 1, value: 'open' },
    ],
    alg: 'sha256(utf8(canonical))',
  });
}
