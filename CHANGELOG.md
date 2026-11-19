# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Oxygen is pre-1.0, so there's no versioned release yet — entries are dated
instead.

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
