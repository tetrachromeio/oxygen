# Oxygen

HTTP/1.1 servers in [Hydrogen](https://github.com/tetrachromeio/hydrogen).
Oxygen is element 8: built on Hydrogen, for the web.

One event loop per core, no allocation per request, no runtime underneath —
see **[Why it's fast](#why-its-fast)**.

```
use Elemental
use Oxygen

new function handle(req: Request, res: Response) {
    if req.get("/") { res.text("Hello, World!") }
    else if req.get("/json") { res.json("{{\"message\":\"Hello, World!\"}}") }
    else { res.not_found() }
}

new function main() -> int { return serve("127.0.0.1", 8080, 0, handle) }   // 0: a loop per core
```

## Status

Pre-1.0. The API in this README is what's shipped and tested; it can still
change. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to build and test it,
and [SECURITY.md](SECURITY.md) to report a vulnerability privately.

## Installation

Oxygen is a Hydrogen library, consumed the way any Hydrogen project depends
on another: a `path` entry in your project's `hy.toml`. There's no package
registry yet, so clone this repo next to (or anywhere relative to) your own
project and point at it:

```bash
git clone https://github.com/tetrachromeio/oxygen
```

```toml
# your-project/hy.toml
[dependencies]
Oxygen = { path = "../oxygen" }
```

You'll also need the Hydrogen compiler (`hy` and `h2c`) on your `PATH`, built
from [tetrachromeio/hydrogen](https://github.com/tetrachromeio/hydrogen):

```bash
git clone https://github.com/tetrachromeio/hydrogen
cd hydrogen
cmake -S . -B build -G Ninja && cmake --build build
export PATH="$PWD/build/compiler:$PATH"
```

Then, from your project:

```bash
hy build --release --native && ./build/your-project
```

## Quick start

```bash
git clone https://github.com/tetrachromeio/oxygen
cd oxygen/examples/hello
hy build --release --native
./build/hello 8080 1      # port, threads
curl localhost:8080/
```

`examples/hello` has the four endpoints (`/`, `/json`, `/bytes`, `POST /echo`)
used for the numbers below. `examples/selftest` is the test suite (see
[Testing](#testing)).

## Speed

Linux x86, 4 cores; server on its own cores, `wrk -c64` on the others:

| | cores | `/` req/s | `/json` req/s | p99 `/` | memory | startup |
|---|---|---|---|---|---|---|
| **Oxygen** | 1 | **168k-182k** | **162k-189k** | 0.7-0.9 ms | 2 MB | **1.9 ms** |
| Rust axum (tokio) | 1 | 99k-108k | 97k-105k | 1.1-2.0 ms | 4 MB | 2.8 ms |
| Node 22 (`http`) | 1 | 44k | 45k | 3.1 ms | 81 MB | 38 ms |
| FastAPI (uvicorn + uvloop) | 1 | 12.7k | 11.8k | 6.8 ms | 48 MB | 257 ms |
| **Oxygen** | 2 | **300k-303k** | **294k-301k** | 0.31-0.37 ms | 3 MB | |
| Rust axum | 2 | 175k | 167k | 0.77 ms | 6 MB | |
| FastAPI, 2 workers | 2 | 24.7k | 21.4k | 4.7 ms | | |

About 1.7x axum, 4x Node and 14x FastAPI per core. At 2 cores the load
generator (also 2 cores) may be the limit, so 300k is a lower bound. These are
hello-world tests: they measure the server's own cost (parsing, dispatch,
writing), which is what Oxygen controls. Startup is launch to the first
complete response, median of 20 runs.

The benchmark kit used to produce these numbers (wrk scripts, comparison
servers in Rust/Node/Python, startup/footprint harnesses) isn't published in
this repo yet.

## Why it's fast

- **One event loop per core** (epoll on Linux, kqueue on macOS), each with its
  own listening socket that the kernel spreads connections across (Linux).
  Loops share nothing: no locks, no work stealing, no atomics on the request
  path.
- **No allocation per request.** Each connection keeps an input and an output
  buffer across requests. A `Request` is views (method, path, query, headers,
  body) into the input buffer, so nothing is copied. A `Response` writes
  status line, headers and body straight into the output buffer.
- **One send per read.** Everything a read produced (pipelined requests
  included) goes out in one `send()`. The `Date` header is formatted once a
  second.
- **No runtime underneath.** No async executor, no garbage collector, no
  interpreter: the loop is ordinary Hydrogen compiled to native code.

## API

### `Request`
| | |
|---|---|
| `req.get(path)` `req.post(path)` `req.is(method, path)` | route matching (`get` also answers `HEAD`, without the body) |
| `req.method` `req.path` `req.query` `req.target` `req.body` | views (valid during the handler) |
| `req.header(name)` | value of a header, any case, or `""` |
| `req.param_text(name)` | a query parameter, percent-decoded (`+` as space): `Some(value)` or `None` |
| `req.param(name)` | the same, raw (a view: no copy) |
| `req.decoded_path()` | the path, percent-decoded |
| `req.header_count`, `req.header_at(i)` | all headers |
| `req.match_prefix(prefix)` | if the path is `prefix`, or starts with it at a `/` boundary, the rest of the path (a view: no copy) — `Some(rest)` or `None`; a `prefix` itself ending in `/` matches anything after it, boundary or not |

### `Response`
| | |
|---|---|
| `res.text(body)` `res.json(body)` `res.html(body)` | 200 with that content type |
| `res.send(status, content_type, body)` | anything else; the `Content-Type` header is dropped (not sent) if `content_type` contains CR or LF |
| `res.not_found()` `res.status(code)` | status with its reason as the body |
| `res.header(name, value)` | extra header (before sending); ignored if `name`/`value` contain CR or LF, or if the response is already sent |
| `res.close()` | close the connection after this response |
| `res.begin_events()`, `res.event(data)`, `res.end_events()` | Server-Sent Events, each event sent at once; `event` returns false once the client has gone |

A handler that doesn't answer gets a 500. Requests are answered in order;
keep-alive is the default for HTTP/1.1. Request bodies may come with
`Content-Length` or chunked (decoded in place: `req.body` is still a view);
`Expect: 100-continue` is answered so clients send large bodies at once.
`url_decode(text, plus_as_space)` is available on its own.

**Always treat path/query/header values and the body as untrusted.** Oxygen
rejects CR/LF reaching `res.header()`, but it has no idea what your own
`res.html`/`res.json`/`res.send` bodies contain — escape user input yourself
before putting it in HTML or building JSON by hand.

### `serve(host, port, threads, handler)`, `serve_with(host, port, threads, context, handler)`
Runs `threads` event loops (0: one per core). The handler is a plain function
(no captured variables), so every loop can call it. `serve_with` hands
`context` (a pointer to your app's state) to every request as `req.context`;
with several threads, that state must be safe to share.

**Graceful shutdown:** both install a SIGTERM/SIGINT handler before starting.
On either signal, every loop stops accepting new connections and finishes
draining the ones it has (including letting an in-flight, not-yet-complete
request finish); `serve`/`serve_with` return once all of them have. A
connection that was simply sitting idle at the time (not actively mid-request)
drains via the same idle timeout below, rather than being cut off early —
within a bound, not held open indefinitely either.

## Modules

Opt-in layers on top of the core, each its own submodule — `use Oxygen` alone
never pulls one in, so a service that doesn't need it pays nothing for it.

### `Oxygen.Static`

Serves a directory of static files, with path-traversal protection,
`ETag`/`Last-Modified` caching, `HEAD`, and `Range`:

```
use Oxygen
use Oxygen.Static

new function handle(req: Request, res: Response) {
    if serve_static("/var/www/public", req, res) { return }
    res.not_found()
}
```

- `serve_static(root, req, res) -> bool`: `true` if it served the request
  (including an error status for something that exists but couldn't be
  read) — the caller should stop, not fall through to its own 404. `false`
  if there's nothing to serve here (wrong method, no such file, or path
  traversal) — the caller continues as normal.
- **Path traversal is the load-bearing part of this module.** Both `root`
  and the resolved candidate file are canonicalized (`.`, `..`, and
  symbolic links resolved) before checking the candidate is actually
  inside `root` — not just string-prefixed by it. This catches a plain
  `..`, an encoded one (`req.decoded_path()` already percent-decodes it),
  and a symlink inside `root` pointing outside it. A null byte in the
  decoded path is rejected outright, before any filesystem call.
- `ETag` (from the file's size and mtime) and `Last-Modified`; a matching
  `If-None-Match` or `If-Modified-Since` gets `304` with no body.
- `Range: bytes=...` (a single range; a start, an end, or both, or a
  suffix count) gets `206 Partial Content`; an out-of-bounds range gets
  `416`; more than one range in the header falls back to the whole file as
  a plain `200` (multiple ranges would need a `multipart/byteranges`
  response, which isn't implemented) — a compliant response to a `Range`
  this can't satisfy in the form asked, per RFC 9110 §14.2.
- `HEAD` reuses the core's existing head-only handling (`req.get()` already
  answers `HEAD` the same way as `GET`, without the body) — nothing special
  needed here.

## Limits (for now)

- No TLS: put Oxygen behind a proxy for HTTPS.
- Bodies up to 16 MB, up to 64 headers; transfer encodings other than chunked
  get 501. Chunk extensions and trailer lines are capped (4 KB / 64 KB) rather
  than scanned without limit.
- A connection that pipelines requests faster than it reads responses is
  throttled rather than buffered without limit: once ~1 MB of a connection's
  output is unsent, the server stops reading more from it until the backlog
  drains.
- A handler that takes a long time to *compute* (e.g. streaming generated
  text) holds its loop's other connections until it finishes. Run more
  loops, or keep slow work for dedicated endpoints. Separately, a Server-Sent
  Events connection whose client stops (or slows) *reading* doesn't hold the
  loop forever — the blocking send it uses is capped per call (5s) and in
  total (30s cumulative across the whole response, so a reader that lets just
  enough through right before each call's own timeout can't string it along
  indefinitely), and the connection is dropped once either is hit.
- Requests framed ambiguously (`Content-Length` together with
  `Transfer-Encoding: chunked`, or either header duplicated) are rejected
  rather than guessed at, since a front-end proxy guessing differently is
  exactly how request smuggling happens. The request line and every header
  line must end in a real `\r\n` (a bare `\r` is rejected, not treated as one
  anyway); the HTTP version must be exactly `HTTP/1.0` or `HTTP/1.1`; header
  names must be non-empty tokens (no spaces, no control characters).
- A connection that opens and sends nothing, or sits idle between keep-alive
  requests, is dropped after `OXYGEN_IDLE_TIMEOUT_SECONDS` (default 60); one
  with an incomplete request — bytes received, but no complete header block
  yet (Slowloris-style) — after the shorter `OXYGEN_HEADER_TIMEOUT_SECONDS`
  (default 10). A request whose headers are complete but whose body is still
  arriving (a slow upload) gets the idle timeout, not the header one, since
  that's legitimate. Checked on the existing once-a-second tick, so neither
  costs an extra syscall. Both env vars are read once per worker thread at
  startup, not on every check.
- No built-in per-IP or connection-count limiting; that's a proxy/OS job, not
  this framework's.

See [SECURITY.md](SECURITY.md) for how to report problems with this list
being wrong (e.g. something above being bypassable) versus just living with
it.

## Testing

```bash
cd examples/selftest
hy build --release --native
./build/selftest
```

`examples/selftest` serves on a free port and talks to itself over real
sockets: every response path, query (raw and percent-decoded), headers, POST
bodies (sized, chunked with extensions and trailers, `Expect: 100-continue`),
pipelining, HTTP/1.0, HEAD, events, malformed input. See
[CONTRIBUTING.md](CONTRIBUTING.md) for running it against the full Hydrogen
test suite and what's expected to match.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) — please report vulnerabilities privately
rather than as a public issue.

## License

[MIT](LICENSE)
