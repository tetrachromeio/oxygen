# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Oxygen is pre-1.0, so there's no versioned release yet — entries are dated
instead.

## 2026-11-19 — `Oxygen.Codec`

From [#5](https://github.com/tetrachromeio/oxygen/issues/5), part of the
[extended-modules tracking issue](https://github.com/tetrachromeio/oxygen/issues/2).

### Added

- **`Oxygen.Codec`**, a new opt-in submodule: `cookie()`/`set_cookie()`,
  `parse_form()`, `parse_multipart()`/`parse_multipart_body()`, and
  `json_body()` (a one-line convenience over `Elemental.Json`'s existing
  `JsonReader`, not a reimplementation).
- `set_cookie()` reuses `Response.header()`'s CR/LF rejection and
  additionally drops `;` in the name/value, since that corrupts the
  cookie's own structure even without being a header-injection risk.
- `parse_multipart()` is strict: a malformed body returns `None` rather
  than a best-effort guess, per the issue's explicit ask given multipart
  parsing's history of parser-differential bugs. Handles both quoted and
  unquoted `boundary=` in `Content-Type`.

No core changes needed — fully additive.

Verified in `examples/codec` (11 cases, all passing): cookie present/absent,
`set_cookie`'s exact header value (including the Max-Age path), a `;` in a
cookie value correctly dropping it instead of corrupting it, percent-decoded
form parsing, a two-part multipart body (one with a filename), a malformed
multipart body rejected, a quoted boundary, and the JSON convenience. Caught
two bugs in the test itself while writing it, not in the module: a wrong
`Content-Length` that silently truncated a request body by one byte, and
one that was one byte *too long* and hung the test waiting for a byte that
would never arrive — both from getting `Content-Length` arithmetic wrong by
hand, not anything the module did. Also caught a real test-ordering mistake
that would have looked like a module bug: calling `res.text()` before
`set_cookie()` meant the cookie was silently dropped (headers are ignored
once a response is sent, same rule as `res.header()` always had) — fixed by
reordering the test, not the module.

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
