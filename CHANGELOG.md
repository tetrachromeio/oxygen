# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Oxygen is pre-1.0, so there's no versioned release yet — entries are dated
instead.

## 2026-11-19 — `Oxygen.Test`: in-process request/response harness

From [#8](https://github.com/tetrachromeio/oxygen/issues/8), part of the
Extended/Ecosystem tracking issue [#2](https://github.com/tetrachromeio/oxygen/issues/2).

### Added

- **`Oxygen.Test`**: `dispatch(handler, raw_request) -> TestResponse` runs a
  `Handler` against a raw HTTP request with no socket, no port, and no
  thread — for fast, deterministic tests that don't need to be safe to run
  many of in parallel against real ports.
- **`dispatch_in_memory(handler, raw_request) -> string`**, new on the core
  (`parse.h2`): builds a dummy, fd-less `Conn` and feeds it through the
  existing private `answer()` — the same parser and dispatch path a real
  connection uses — so the test harness has nothing of its own to drift out
  of sync with the real one.
- `TestResponse` owns its header/body bytes (a new `TestHeader` type, not
  the core's view-based `Header`): the raw response text it's parsed from is
  a short-lived local inside `dispatch()`, gone by the time the caller gets
  a `TestResponse` back, so a zero-copy view into it would dangle. Caught by
  design review before writing the parser, not by a crash.

### Measured

- `examples/testharness` checks `dispatch()`'s output byte-for-byte (minus
  the ticking `Date` header) against the same requests over a real loopback
  socket, across six request shapes (root, query string, missing query
  param, header read, POST body, 404).
- 2000 iterations: `dispatch()` 0.00234s vs. a real socket round-trip
  0.12351s — about **53x** faster, the actual point of an in-process
  harness rather than something to assume.
## 2026-11-20 — connection peer address, trusted-proxy header extraction

From [#10](https://github.com/tetrachromeio/oxygen/issues/10) and
[#11](https://github.com/tetrachromeio/oxygen/issues/11), part of the
[extended-modules tracking issue](https://github.com/tetrachromeio/oxygen/issues/2).

### Added

- **`req.peer`** on `Request`: the TCP peer's `"ip:port"` (IPv6 bracketed),
  captured once at `accept()` time via a new `getpeername`-based runtime
  primitive (`h2_sock_peer_addr` in the hydrogen repo, wrapped as
  `Elemental.Net.sock_peer_addr`) — no per-request syscall, and re-captured
  on every `accept()` since a connection slot (indexed by fd) gets reused by
  later, unrelated connections once one closes.
- **`Oxygen.Middleware.trusted_proxy_addr(req, trusted)`**: the real client
  address, honoring `Forwarded`/`X-Forwarded-For` only when `req.peer` is
  itself in `trusted` — an untrusted peer's headers are ignored outright,
  the one case that actually matters here. A multi-hop chain resolves to
  the right-most entry that *isn't* in `trusted` (chained trusted proxies
  skipped over), not naively the first or last item. v1 is exact-IP
  matching only, no CIDR ranges — not found to be a real limitation while
  building this, but flagging it rather than growing this preemptively.

### Tested

- `examples/middleware`: a trusted peer with no forwarded header (returns
  `req.peer`), a trusted peer with one forwarded hop, a trusted peer with a
  two-hop chain where the nearer hop is itself a trusted proxy (resolves to
  the far hop, not the near one), an untrusted peer's forged
  `X-Forwarded-For` being ignored, and `Forwarded`'s `for=` being read
  alongside `X-Forwarded-For`.
- IPv6 peer formatting (`"[::1]:port"`) is implemented per the standard
  `getpeername`/`inet_ntop` pattern but unverified in this environment: the
  cloud sandbox this was built in has no IPv6 support at all (confirmed:
  `socket(AF_INET6, ...)` itself fails with `EAFNOSUPPORT`). IPv4 verified
  against a real client's own observed source port.

## 2026-11-19 — `Oxygen.Middleware`

From [#4](https://github.com/tetrachromeio/oxygen/issues/4), part of the
## 2026-11-19 — `Oxygen.Router`

From [#3](https://github.com/tetrachromeio/oxygen/issues/3), part of the
[extended-modules tracking issue](https://github.com/tetrachromeio/oxygen/issues/2).

### Added

- **`Oxygen.Middleware`**, a new opt-in submodule: `cors()`,
  `add_security_headers()`, `request_id()`, `log_access()` — plain
  functions called directly from your own handler, not `Handler`-wrapping
  decorators (settled design question from the issue: Oxygen's core
  `Handler` can't capture variables, so a literal
  `wrap_cors(handler) -> Handler` isn't possible the way the issue first
  sketched it).
- **`Response.status_code()`**, a small core addition this needed: the
  status a response was sent with, or `0` before it has been. Set once, in
  `head()` — the single place every send path (`send`, `status`,
  `begin_events`) already goes through.

### Deferred

- Trusted-proxy header extraction (`Forwarded`/`X-Forwarded-For`). Doing it
  safely means only honoring those headers when the immediate TCP peer is
  itself a trusted proxy, and the core doesn't expose a connection's peer
  address to a handler at all yet. Shipping it without that would mean
  trusting every client's `Forwarded` header unconditionally — exactly the
  vulnerability this is supposed to prevent — so it's deferred rather than
  shipped half-safe. Split out to
  [#11](https://github.com/tetrachromeio/oxygen/issues/11), blocked on
  [#10](https://github.com/tetrachromeio/oxygen/issues/10) (exposing a
  connection's peer address on `Request` — a real core gap found while
  building this, not originally in scope).
- **`Oxygen.Router`**, a new opt-in submodule: dynamic path params
  (`/users/:id`), a wildcard tail (`/static/*path`), `router.group(prefix)`
  for a prefixed sub-router, automatic `405 Method Not Allowed` with an
  `Allow` header, and automatic `OPTIONS`. Route handlers take
  `(Request, Response, Params)`; `Params.get(name)` returns a captured
  segment as a zero-copy view into `req.path`.
- Dispatches through the existing `context` mechanism
  (`dispatch_handler` + a `Router` as context), the same way any other
  shared app state reaches a handler.

### Measured

- Linear scan vs. a trie: a 50-route table (mixed literal/dynamic segments)
  takes ~0.3us per dispatch, regardless of whether the match is the first
  route, the last, or no match at all after scanning everything. Against the
  ~5.5us/request budget implied by the ~180k req/s/core number above, that's
  about 5% of it in the worst case — real, but not dominant at this scale.
  Kept the linear scan; a trie would matter more for a route table orders of
  magnitude larger, or traffic that's mostly 404s.
- No heap allocation on a successful dispatch (checked by inspection — the
  only allocation in `handle()` is on the 405/`Allow`-building path, not the
  match-and-call path) and no RSS growth over 10,000 real requests against a
  running server (2516KB -> 2524KB; the few KB of noise is connection/OS
  churn, not a per-request leak).

## 2026-11-19 — idle/header timeouts, graceful shutdown, `match_prefix`

From [#1](https://github.com/tetrachromeio/oxygen/issues/1).

### Added

- **Idle and incomplete-header timeouts.** A connection with no activity
  (`OXYGEN_IDLE_TIMEOUT_SECONDS`, default 60) or an incomplete request
  (`OXYGEN_HEADER_TIMEOUT_SECONDS`, default 10 — shorter, to give less
  patience to a Slowloris-style drip-feed than to a connection simply idling
  between keep-alive requests) is now dropped rather than held open
  indefinitely. Both ride the event loop's existing once-a-second tick, so
  neither costs an extra syscall; both env vars are read once per worker
  thread at startup.
- **Graceful shutdown.** `serve`/`serve_with` now install a SIGTERM/SIGINT
  handler: either stops every loop from accepting new connections and lets
  what's already open — including an in-flight, not-yet-complete request —
  finish, rather than cutting everything off mid-request.
- **`Request.match_prefix(prefix)`** — `Some(rest)` as a zero-copy view into
  `req.path` if it starts with `prefix` at a `/` boundary, `None` otherwise,
  for routers built on top of Oxygen that peel off a path prefix.

### Investigated, not built

- A SWAR/bitmask-optimized `req.header()` lookup. Measured first, per the
  issue's own acceptance criteria: 2,000,000 iterations of 5 lookups each
  (10,000,000 total, mostly misses against a 3-header request — the worst
  case) took 0.0264s, ~13.2ns per 5 lookups. Against the ~5,560ns per-request
  budget implied by the README's ~180k req/s/core number, that's under 0.25%
  of it. Not worth the complexity; closed as not planned.

## 2026-11-19 — split from the `hydrogen` monorepo

Pulled out of `tetrachromeio/hydrogen`'s `oxygen/` directory into its own
repo (library, examples, README; the benchmark kit wasn't brought over).

### Fixed

- **Header/response injection** via `Response.header()`: CR/LF in `name` or
  `value` reached the wire unfiltered, so unsanitized input passed to it
  (e.g. a redirect target) could split the response and inject arbitrary
  headers or body content. `header()` now ignores calls where either
  argument contains CR or LF, and ignores calls made after the response is
  already sent.
- **Cross-connection header leak**: the header-staging buffer used by
  `Response.header()` was shared by every connection on a worker thread and
  never reset between requests, so a header queued but not flushed for one
  response could be spliced into the *next* response flushed on that
  thread — including another client's. The buffer is now cleared before
  every request.
- **Unbounded memory growth from a chunk extension or trailer line that
  never ends**: the chunked-body parser had no bound on how far it would
  scan for either, so a single connection could grow the server's memory
  without limit. Both are now capped.
- **Unbounded memory growth from pipelined requests the client never
  reads**: a connection could have an unlimited number of requests answered
  into memory before anything was sent, if the client didn't read its
  responses. The server now stops answering further pipelined requests and
  stops reading more from that connection once its unsent output crosses a
  threshold, until the backlog drains — real backpressure, via the kernel's
  own flow control, rather than an unbounded buffer.

See the security review sent alongside this split for reproduction details
and verification of each fix.

## 2026-11-19 — 8 more parsing/DoS issues from a follow-up review

- **HTTP request smuggling (CL.TE/TE.CL)**: a request with both
  `Content-Length` and `Transfer-Encoding: chunked`, or a duplicate
  `Content-Length`/`Transfer-Encoding` header, is now rejected (400) rather
  than silently picking one interpretation — a front-end proxy picking the
  other could let a client smuggle a second, hidden request past it.
- **`Content-Length` integer overflow**: the digit accumulator is now
  bounded to 10 digits (413 beyond that), rather than relying only on a
  post-add `> MAX_BODY_BYTES` check that an overflow could land back under,
  unnoticed, producing a negative/huge body length and an out-of-bounds
  read when a handler touches `req.body`.
- **Server-Sent Events could freeze a whole worker thread forever**:
  `begin_events()`'s blocking `send()` had no timeout, so a reader that
  stopped reading could block it indefinitely, stalling every other
  connection on that thread. Bounded with a new `sock_send_timeout()` — and,
  after testing the fix turned up that a per-call timeout alone isn't
  sufficient (a reader that lets just enough through right before each call's
  own timeout, never actually failing one, could still string a connection
  along in increments of it forever), a running total across the whole
  response's sends, capped independently of any individual call's outcome.
- **Permanent peak buffer retention**: a connection that ever handled
  something large kept that buffer allocation for the rest of the server's
  life. `close_conn()` now shrinks it back down past a threshold, and one
  `recv()` call is now capped so it can't pull in an entire large pipelined
  burst before the existing backpressure gets a chance to apply.
- **O(N²) CPU cost from a drip-fed header block**: the header-terminator
  scan restarted from the top on every read. A per-connection cursor now
  resumes near where the last scan left off.
- **Lenient parsing that could desync from a front-end proxy**: a bare CR
  not followed by LF in the request line or a header line is now rejected
  (400) instead of silently treated as a line ending; the HTTP version must
  now be exactly `HTTP/1.0` or `HTTP/1.1`; header names must be non-empty
  RFC 9110 tokens.
- **`res.send()`'s `content_type` wasn't checked for CRLF** the way
  `res.header()` is, so an app passing it unsanitized input could still
  split the response. Now dropped the same way `header()` handles it.
- **Half-closed (FIN) clients could get a truncated response**: a client
  that `shutdown(SHUT_WR)`s right after its request, while still reading
  the response, had its connection closed immediately rather than once its
  pending output had actually drained.
