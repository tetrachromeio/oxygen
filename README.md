# Oxygen

HTTP/1.1 servers in Hydrogen. Oxygen is element 8: built on Hydrogen, for the web.

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

## Speed

Same machine, same sitting (Linux x86, 4 cores; server on its own cores, `wrk -c64`
on the others; method and scripts in `bench/`, goals in `docs/OXYGEN_GOALS.md`):

| | cores | `/` req/s | `/json` req/s | p99 `/` | memory | startup |
|---|---|---|---|---|---|---|
| **Oxygen** | 1 | **168k-182k** | **162k-189k** | 0.7-0.9 ms | 2 MB | **1.9 ms** |
| Rust axum (tokio) | 1 | 99k-108k | 97k-105k | 1.1-2.0 ms | 4 MB | 2.8 ms |
| Node 22 (`http`) | 1 | 44k | 45k | 3.1 ms | 81 MB | 38 ms |
| FastAPI (uvicorn + uvloop) | 1 | 12.7k | 11.8k | 6.8 ms | 48 MB | 257 ms |
| **Oxygen** | 2 | **300k-303k** | **294k-301k** | 0.31-0.37 ms | 3 MB | |
| Rust axum | 2 | 175k | 167k | 0.77 ms | 6 MB | |
| FastAPI, 2 workers | 2 | 24.7k | 21.4k | 4.7 ms | | |

Startup: launch to the first complete response, median of 20 (`bench/startup.py`).

About 1.7x axum, 4x Node and 14x FastAPI per core. At 2 cores the load generator
(also 2 cores) may be the limit, so 300k is a lower bound. These are hello-world
tests: they measure the server's own cost (parsing, dispatch, writing), which is
what Oxygen controls.

## Why it's fast

- **One event loop per core** (epoll on Linux, kqueue on macOS), each with its own
  listening socket that the kernel spreads connections across (Linux). Loops share
  nothing: no locks, no work stealing, no atomics on the request path.
- **No allocation per request.** Each connection keeps an input and an output
  buffer across requests. A `Request` is views (method, path, query, headers,
  body) into the input buffer, so nothing is copied. A `Response` writes status
  line, headers and body straight into the output buffer.
- **One send per read.** Everything a read produced (pipelined requests included)
  goes out in one `send()`. The `Date` header is formatted once a second.
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

### `Response`
| | |
|---|---|
| `res.text(body)` `res.json(body)` `res.html(body)` | 200 with that content type |
| `res.send(status, content_type, body)` | anything else |
| `res.not_found()` `res.status(code)` | status with its reason as the body |
| `res.header(name, value)` | extra header (before sending) |
| `res.close()` | close the connection after this response |
| `res.begin_events()`, `res.event(data)`, `res.end_events()` | Server-Sent Events, each event sent at once; `event` returns false once the client has gone |

A handler that doesn't answer gets a 500. Requests are answered in order;
keep-alive is the default for HTTP/1.1. Request bodies may come with
`Content-Length` or chunked (decoded in place: `req.body` is still a view);
`Expect: 100-continue` is answered so clients send large bodies at once.
`url_decode(text, plus_as_space)` is available on its own.

### `serve(host, port, threads, handler)`, `serve_with(host, port, threads, context, handler)`
Runs `threads` event loops (0: one per core) and never returns unless it can't
listen. The handler is a plain function (no captured variables), so every loop
can call it. `serve_with` hands `context` (a pointer to your app's state) to
every request as `req.context`; with several threads, that state must be safe
to share.

An app built on it: `carbon/examples/serve`, an OpenAI-compatible API for Carbon.

## Limits (for now)

- No TLS: put Oxygen behind a proxy for HTTPS.
- Bodies up to 16 MB, up to 64 headers; transfer encodings other than chunked get 501.
- A handler that takes a long time (e.g. streaming generated text) holds its
  loop's other connections until it finishes. Run more loops, or keep slow work
  for dedicated endpoints.
- No idle-connection timeouts yet.

## Tests

`oxygen/examples/selftest` serves on a free port and talks to itself over real
sockets: every response path, query (raw and percent-decoded), headers, POST
bodies (sized, chunked with extensions and trailers, `Expect: 100-continue`),
pipelining, HTTP/1.0, HEAD, events, malformed input. Part of `tests/run_tests.py`.
