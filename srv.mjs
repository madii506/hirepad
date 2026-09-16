// Local stand-in for Vercel: serves the static site and runs the real api/*.js
// handlers, shimming req.query and res.status().json() the way Vercel does.
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = process.cwd();
const PORT = 8833;
const MIME = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css',
  '.png':'image/png', '.jpg':'image/jpeg', '.svg':'image/svg+xml', '.json':'application/json',
  '.ico':'image/x-icon', '.woff2':'font/woff2' };

function shim(res){
  res.status = (c)=>{ res.statusCode = c; return res; };
  res.json = (o)=>{ res.setHeader('content-type','application/json'); res.end(JSON.stringify(o)); return res; };
  res.send = (b)=>{ res.end(b); return res; };
  return res;
}

http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  shim(res);

  if (u.pathname.startsWith('/api/')) {
    const file = join(ROOT, u.pathname.replace(/\/+$/,'') + '.js');
    try {
      const mod = await import(pathToFileURL(file).href + '?t=' + Date.now());
      req.query = Object.fromEntries(u.searchParams);
      await mod.default(req, res);
      if (!res.writableEnded) res.end();
    } catch (e) {
      res.status(500).json({ error: String(e && e.message || e) });
    }
    return;
  }

  let p = normalize(u.pathname === '/' ? '/index.html' : u.pathname).replace(/^(\.\.[/\\])+/, '');
  const file = join(ROOT, p);
  try {
    await stat(file);
    const body = await readFile(file);
    res.setHeader('content-type', MIME[extname(file)] || 'application/octet-stream');
    res.end(body);
  } catch {
    res.statusCode = 404; res.end('not found');
  }
}).listen(PORT, () => console.log('serving on http://127.0.0.1:' + PORT));
