import { createReadStream, existsSync } from 'node:fs'
import { extname, join } from 'node:path'
import { createServer } from 'node:http'
import { fileURLToPath } from 'node:url'

const port = Number(process.env.PORT || 5174)
const root = fileURLToPath(new URL('./dist/', import.meta.url))

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
}

function proxyApi(req, res) {
  const target = new URL(req.url, 'http://localhost:8000')
  const hasBody = !['GET', 'HEAD'].includes(req.method)
  fetch(target, {
    method: req.method,
    headers: req.headers,
    body: hasBody ? req : undefined,
    ...(hasBody ? { duplex: 'half' } : {}),
  })
    .then(async (apiRes) => {
      res.writeHead(apiRes.status, Object.fromEntries(apiRes.headers))
      if (apiRes.body) {
        for await (const chunk of apiRes.body) res.write(chunk)
      }
      res.end()
    })
    .catch(() => {
      res.writeHead(502, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ detail: 'Backend API is not reachable' }))
    })
}

function serveFile(req, res) {
  const url = new URL(req.url, `http://127.0.0.1:${port}`)
  const requestedPath = decodeURIComponent(url.pathname.replace(/^\/+/, ''))
  const filePath = join(root, requestedPath || 'index.html')
  const finalPath = existsSync(filePath) && !filePath.endsWith('/') ? filePath : join(root, 'index.html')
  const ext = extname(finalPath)

  // Hashed build assets (dist/assets/*) are content-addressed — a change
  // produces a new filename — so they can cache forever. Everything else
  // (index.html, manifest) stays no-cache so new builds are picked up. This
  // is what makes repeat loads / iOS backgrounded-tab reloads instant on a
  // phone instead of re-downloading the whole bundle every time.
  const isHashedAsset = requestedPath.startsWith('assets/')
  res.writeHead(200, {
    'cache-control': isHashedAsset
      ? 'public, max-age=31536000, immutable'
      : 'no-cache',
    'content-type': contentTypes[ext] || 'application/octet-stream',
  })
  createReadStream(finalPath)
    .on('error', () => {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' })
      res.end('Not found')
    })
    .pipe(res)
}

createServer((req, res) => {
  console.log(new Date().toISOString(), req.method, req.url)
  if (req.url.startsWith('/api/')) {
    proxyApi(req, res)
    return
  }
  serveFile(req, res)
}).listen(port, () => {
  console.log(`Mickeymouse House web app: http://localhost:${port}`)
})
