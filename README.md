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
change. See [ROADMAP.md](ROADMAP.md) for what 1.0 means and what's left,
[CONTRIBUTING.md](CONTRIBUTING.md) for how to build and test it, and
[SECURITY.md](SECURITY.md) to report a vulnerability privately.

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

- **One event loop per core** (epoll on Linux, kqueue on macOS; `select()` on
  Windows — see **Limits**), each with its
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
| `req.peer` | the TCP peer's address as `"ip:port"` (IPv6 bracketed: `"[::1]:port"`), captured once at `accept()` — not a per-request syscall. Don't trust it as the "real" client address behind a reverse proxy without checking it's that proxy first — see `Oxygen.Middleware`'s `trusted_proxy_addr` |

### `Response`
| | |
|---|---|
| `res.text(body)` `res.json(body)` `res.html(body)` | 200 with that content type |
| `res.send(status, content_type, body)` | anything else; the `Content-Type` header is dropped (not sent) if `content_type` contains CR or LF |
| `res.not_found()` `res.status(code)` | status with its reason as the body |
| `res.header(name, value)` | extra header (before sending); ignored if `name`/`value` contain CR or LF, or if the response is already sent |
| `res.close()` | close the connection after this response |
| `res.status_code()` | the status this response was sent with, or `0` if it hasn't been yet |
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

### `Oxygen.Middleware`

Cross-cutting concerns (CORS, security headers, request IDs, access
logging) as plain functions you call from your own handler, not
`Handler`-wrapping decorators — Oxygen's core `Handler` can't capture
variables, so there's no closure to wrap one in:

```
use Oxygen
use Oxygen.Middleware

new function handle(req: Request, res: Response) {
    if cors(default_cors(), req, res) { return }   // true: preflight, already answered
    add_security_headers(default_security_headers(), res)
    let id = request_id(req)
    res.header("X-Request-Id", id.view())
    let t0 = now()

    if req.get("/") { res.text("Hello, World!") }
    else { res.not_found() }

    log_access(req, res, id.view(), t0)
}
```

- `cors(config, req, res) -> bool`: adds CORS headers; answers an `OPTIONS`
  preflight itself (204) and returns `true`, meaning the caller should
  return right away rather than continue to its real handler.
  `allow_credentials` with a wildcard `allowed_origin` is invalid per the
  Fetch spec, so that combination sends no `Access-Control-Allow-Credentials`
  rather than a response no browser would honor anyway.
- `add_security_headers(config, res)`: `X-Content-Type-Options: nosniff`
  always; configurable `X-Frame-Options`, `Referrer-Policy`,
  `Content-Security-Policy`, `Strict-Transport-Security`.
- `request_id(req) -> string`: the incoming `X-Request-Id` if there is one,
  otherwise a freshly generated one (not a security token — just enough to
  correlate one request's own log lines).
- `log_access(req, res, id, started_at)`: one line with method, path,
  status, the request id, and latency — call it after your handler answers,
  so `res.status_code()` (new on `Response`, for this) is the real one.

**Trusted-proxy header extraction:**

```
var trusted = List<str>()
trusted.push("10.0.0.1")   // your reverse proxy's address, exactly

new function handle(req: Request, res: Response) {
    let client = trusted_proxy_addr(req, trusted)
    // client is req.peer unless req.peer is itself in `trusted`, in which
    // case it's the right-most address in Forwarded/X-Forwarded-For that
    // *isn't* — i.e. the real client, as reported by a proxy you trust.
}
```

`trusted_proxy_addr(req, trusted) -> str` only honors `Forwarded`
(its `for=` values, RFC 7239) or, failing that, `X-Forwarded-For` when the
immediate TCP peer (`req.peer`, new on `Request`, from `accept()`'s
`getpeername` — no per-request cost) is itself in `trusted`; an untrusted
peer's headers are ignored outright, full stop, since an untrusted client
can set either header to anything. A multi-hop chain resolves to the
right-most entry that *isn't* itself in `trusted` (chained trusted proxies
are skipped over), not naively the first or last item. v1 is exact-IP
matching only, no CIDR ranges.

### `Oxygen.Router`

Dynamic path params (`/users/:id`), a wildcard tail (`/static/*path`),
`router.group(prefix)` for a prefixed sub-router, automatic `405 Method Not
Allowed` + `Allow`, and automatic `OPTIONS`:

```
use Oxygen
use Oxygen.Router

new function get_user(req: Request, res: Response, p: Params) {
    match p.get("id") {
        Some(id) => { res.text("user " + string(id)) }
        None => { res.status(400) }
    }
}

new function main() -> int {
    var router = Router()
    router.get("/users/:id", get_user)
    return serve_with("127.0.0.1", 8080, 1, ptr<u8>(&router), dispatch_handler)
}
```

Route handlers take `(Request, Response, Params)`, not plain `(Request,
Response)` — `Params.get(name)` returns a captured segment as a zero-copy
view into `req.path`, `Some(value)` or `None`. Register every route before
calling `serve`/`serve_with`, not after: dispatch only reads the route table,
but every worker thread reads it without synchronization, the same way
`context` already works for shared app state — which is exactly what this
uses (`req.context` is the `Router`, so bring your own app state via a field
on your own struct that embeds a `Router`, rather than fighting over that one
pointer).

Routes are matched with a linear scan, not a trie: measured at a 50-route
table, ~0.3us/dispatch regardless of where the match lands (first route,
last, or no match at all) — about 5% of the ~5.5us/request budget implied by
this README's ~180k req/s/core number, in the worst case. Real but not
dominant at this scale; a trie would matter more for a route table orders of
magnitude larger, or traffic that's mostly 404s.

## Limits (for now)

- **Windows: compiles and links, unverified by execution.** The runtime
  (`h2rt.c`, hydrogen repo) has a Winsock/`select()`-based port — checked to
  compile and link cleanly against a real `x86_64-w64-mingw32-gcc-posix`
  cross-toolchain, zero warnings even with `-Wall` — but nobody has run the
  resulting binary on actual Windows yet. Known gaps even once it is:
  `select()` is O(n) per wait and capped at 1024 sockets (raised from the
  default 64, but still nowhere near epoll/kqueue's scaling — a real port
  would want IOCP, a different async model entirely); there's no
  `SO_REUSEPORT` equivalent, so `share_port` is a no-op there the same as it
  already is on anything non-Linux; external process termination (service
  stop, Task Manager) doesn't deliver a signal Windows' C runtime forwards
  as `SIGTERM`, so graceful shutdown only works when something in-process
  calls `raise_sigterm()` itself, not from outside.
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

## Modules

Opt-in layers on top of the core, each its own submodule — `use Oxygen` alone
never pulls one in, so a service that doesn't need it pays nothing for it.

### `Oxygen.Test`

An in-process request/response harness: runs your `Handler` against a raw
HTTP request with no socket, no port, and no thread, and hands back the
parsed status, headers and body.

```
use Elemental
use Oxygen
use Oxygen.Test

new function handle(req: Request, res: Response) {
    if req.get("/") { res.text("Hello, World!") }
    else { res.not_found() }
}

new function main() -> int {
    let resp = dispatch(handle, "GET / HTTP/1.1\r\nConnection: close\r\n\r\n")
    assert(resp.status == 200)
    assert(resp.body.view() == "Hello, World!")
    assert(resp.header("Content-Type") == "text/plain")
    return 0
}
```

- `dispatch(handler, raw_request) -> TestResponse`: runs the exact same
  parser and handler dispatch a real connection would (`dispatch_in_memory`,
  new on the core for this — a dummy, fd-less `Conn`, so there's no
  duplicate parser to drift from the real one), and parses the raw response
  back into a `TestResponse`.
- `TestResponse`: `.status`, `.headers` (a `List<TestHeader>`, each a
  `.name`/`.value` pair), `.body`, and `.header(name) -> str` (any case, ""
  if absent — same shape as `Request.header()`). Unlike the core's own
  `Header`, these own their bytes rather than viewing into a buffer: the raw
  response text is a short-lived local inside `dispatch()`, gone by the time
  you get a `TestResponse` back, so a view into it would dangle.

**Not for Server-Sent Events** — `begin_events()`/`event()`/`end_events()`
write straight to a socket, and there isn't one here. Test a streaming
handler the normal way, against real sockets (see `examples/selftest`'s
pattern).

Measured in `examples/testharness`: parity with the real-socket path is
checked byte-for-byte (minus the `Date` header, which ticks) across several
request shapes, and `dispatch()` runs roughly 50x faster per call than the
same requests over a real loopback socket — the actual point of a harness
like this, rather than something to take on faith.

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
