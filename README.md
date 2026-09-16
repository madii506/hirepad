# HIRE

An agent that works for you. Before it starts a job it posts a **bond** onchain
equal to what you paid, out of its own wallet, against a hash of the exact terms
and a deadline. Deliver and the bond returns and it keeps the fee. Miss the
deadline and the bond is yours, along with your fee back — in dollars, through
X Money. Nothing to claim.

**It works. It bonds every job. If it fails, it pays you.**

## The rule

1. **The job is hashed.** Terms, price, bond and deadline become one canonical
   string, and `sha256` of it *is* the job. A one-character edit is a different
   job with a different hash.
2. **The bond opens before work starts.** An amount equal to your price, staked
   from the agent's own wallet. It cannot begin without this and cannot open a
   bond it cannot cover.
3. **Proof is filed** in the public thread the job was agreed in. Filing proof
   settles nothing by itself.
4. **The deadline settles it.** Proof in time → delivered. No proof → failed,
   and **anyone** can call `expire()` to force that settlement.

Nobody grades the work. A quality standard can be argued with; a deadline
cannot. That trade-off is stated plainly in the docs rather than hidden.

## Why bond = price

| outcome | the agent | you |
| --- | --- | --- |
| delivered | + the fee, bond returns | you paid the fee and got the work |
| failed | − the bond, fee refunded | your fee back, plus the bond on top |

The swing between delivering and failing is **twice the price**, and the agent's
downside is exactly your upside. A smaller bond makes failure cheap; a larger one
makes it refuse work it could do.

## The ceiling

```
ceiling    = wallet_balance          # the bond must be covered
can_accept = 0 < price <= ceiling
after_win  = balance + price
after_loss = balance − price
```

The largest job it can take is the size of its own wallet. Earning raises it,
failing lowers it, and a failing agent prices itself out of the market without
anyone intervening. The creator fee on $HIRE funds the wallet, so volume does
exactly one thing here: it raises the ceiling.

## The commitment format

```
HIRE/v1
job=<whitespace collapsed, trimmed, max 2000 chars>
price=<integer cents>
bond=<integer cents>
deadline=<integer hours>h
```

`job_hash = sha256(utf8(canonical))`. Whitespace is collapsed before hashing so
a stray double space can't fork the hash; money is in integer cents so no float
touches a commitment; the version prefix stops a future format change silently
reinterpreting an old hash.

The front page hashes this in your browser with Web Crypto **and** independently
on the server, then prints both. Verify it a third way:

```sh
printf 'HIRE/v1\njob=%s\nprice=%s\nbond=%s\ndeadline=%sh' \
  "read the replies and summarise them" 4000 4000 24 | sha256sum
```

## Readers

Five endpoints, no database, nothing that writes. Each is documented with a live
"try it" button in [`/docs.html`](docs.html).

| endpoint | reads | source |
| --- | --- | --- |
| `/api/bond?job=&price=&deadline=` | the commitment hash and account layout | computed here |
| `/api/tweet?id=` | a post, for proof and threads | FxTwitter, then syndication |
| `/api/handle?h=` | an account's name and followers | FxTwitter, then syndication |
| `/api/avatar?h=` | an account's picture (proxied bytes) | resolved, then proxied |
| `/api/coin?ca=&fee=` | volume, and the fee funding the wallet | Dexscreener, solana only |

Only FxTwitter can carry view counts, and not for every post. Either way `views`
comes back `null` and never `0` — a null is not a zero.

## The operator

X Money accounts belong to people, so a human taps send. That human decides
nothing: the bond, amount, recipient and outcome are fixed onchain first. They
hold no key to the program. What they *could* do wrong, and where you would catch
them, is published in the docs rather than glossed over.

## Status

$HIRE has **no mint address yet**. When one exists it will be on the site and in
the pinned post at the same moment. Anyone posting an address before that is
scamming you.

The program is specified but not deployed, no bond has been opened, and the
ledger is empty. Every figure on the site reads as a dash rather than a zero,
because a zero would claim we looked and found nothing.

## Running it

```sh
node srv.mjs      # local stand-in for Vercel on :8833
python3 test.py   # playwright suite against the local server
```

The suite checks, among other things, that the browser's SHA-256 and the
server's agree, that the published canonical string really hashes to the digest
shown, and that a one-character edit moves it.
