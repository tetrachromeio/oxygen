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
