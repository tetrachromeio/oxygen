# Contributing to Oxygen

Thanks for considering it. Oxygen is small and deliberately so — most
contributions should be bug fixes, test cases, or docs; new features should
have a clear use case and fit the "no allocation per request, no runtime
underneath" design, not add either.

## Layout

One module (`use Oxygen`), split across files by concern — all `include`d
from `init.h2`, which is otherwise just the module doc comment and `use`
lines (see [spec/syntax.md](https://github.com/tetrachromeio/hydrogen/blob/main/spec/syntax.md#multi-file-modules-include)
in the hydrogen repo for how `include` works):

| File | What's in it |
|---|---|
| `limits.h2` | the tunable limits (`MAX_BODY_BYTES` and the rest) |
| `buffer.h2` | the growable byte buffer requests and responses are built from |
| `request.h2` | `Header`, `Request`, and the header/query parsing helpers |
| `response.h2` | `Response`, including Server-Sent Events, and the `Handler` type |
| `parse.h2` | the HTTP/1.1 parser: headers, chunked bodies, pipelining |
| `loop.h2` | the event loop, and the public `serve()` / `serve_with()` |

All of them share one namespace (a non-`pub` item in `parse.h2` is visible
from `loop.h2`, say), so put something where a reader looking for it would
look first, not necessarily where it's used.

## Setup

You'll need the Hydrogen compiler. There's no release binary yet, so build
it from source:

```bash
git clone https://github.com/tetrachromeio/hydrogen
cd hydrogen
cmake -S . -B build -G Ninja && cmake --build build   # needs CMake >= 3.20, a C++20 compiler, Python 3, clang
export PATH="$PWD/build/compiler:$PATH"
```

Then clone this repo and build the examples:

```bash
git clone https://github.com/tetrachromeio/oxygen
cd oxygen/examples/hello
hy build --release --native
./build/hello 8080 1
```

## Running the tests

```bash
cd examples/selftest
hy build --release --native
./build/selftest
```

That prints every test's request and response. If you have a checkout of
[tetrachromeio/hydrogen](https://github.com/tetrachromeio/hydrogen) too, its
`tests/oxygen/selftest.out` is the expected output — `selftest`'s output
should match it byte for byte (aside from the `Date:` header, which changes
every run):

```bash
diff <(./build/selftest) /path/to/hydrogen/tests/oxygen/selftest.out
```

If you're adding a test case, add it to `examples/selftest/main.h2` and
update the expected output in the `hydrogen` repo's `tests/oxygen/` in the
same change (open a PR there too, or say so in this repo's PR — a maintainer
will sync it).

## Making a change

1. Open an issue first for anything beyond a small fix, so the approach gets
   agreed on before you write code — especially for anything touching
   `init.h2`'s request parser or the event loop, where correctness bugs are
   easy to introduce and easy to miss.
2. Keep the style of the file you're editing: `pub` for the public API,
   `new function`/`new type` for everything internal to the module, one-line
   comments explaining *why*, not restating the code. Look at the function
   you're changing and match it.
3. **Any change to parsing (headers, chunked bodies, pipelining) needs a
   `examples/selftest` case that would have failed before your fix.** This
   code parses untrusted input from the network; "it works for the happy
   path locally" isn't enough. Prefer a minimal client-level test (raw bytes
   in, raw response out) over one that only exercises it through the
   high-level API.
4. For anything performance-sensitive, say in the PR what you measured and
   how (machine, `wrk` settings or equivalent, before/after numbers) — see
   the README's **Speed** section for the format. Don't guess at perf
   effects; measure them.
5. Run the test above and make sure it still matches before opening the PR.

## Reporting bugs

If it's a security issue — something that lets a client crash the server,
read/corrupt memory, inject into another response, leak data across
connections, or blow up the server's memory/CPU with a small amount of
input — see [SECURITY.md](SECURITY.md) and report it privately instead of
as a public issue.

For anything else, a GitHub issue with a minimal repro is ideal: the handler
code and the exact request (or a `curl`/raw-bytes example) that shows the
problem.

## Code of conduct

Be respectful and assume good faith. Technical disagreements go into the
PR/issue thread on their merits; ad hominem, harassment, or bad-faith
arguing get the thread locked and, if it continues, the person blocked.
