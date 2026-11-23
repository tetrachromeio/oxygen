# Road to 1.0

Oxygen is pre-1.0 ([README](README.md#status)): the shipped API is tested,
but nothing guarantees it won't change. This is what "1.0" means here and
what's left to get there. Checked items are done; unchecked are not.

1.0 doesn't mean "feature-complete forever" — it means: the core API is
frozen, what's shipped is actually merged and tagged, and the project has a
process that catches a regression before a user does. Everything below is in
service of that, not growth for its own sake.

## API stability

- [x] `Request`, `Response`, `Handler`, `serve`/`serve_with` have been
      stable for a while — this is a formality, not a change.
- [ ] **Freeze the core API at 1.0.** After this, a breaking change to
      `Request`/`Response`/`serve`/`serve_with` needs a major version bump,
      not a changelog entry.
- [ ] Decide whether the 6 submodules (`Router`, `Middleware`, `Codec`,
      `Static`, `WS`, `Test`) are 1.0-stable too, or ship as "0.x extras"
      for a release or two first. Recommendation: freeze the core now;
      let the modules season through a 1.0 release before freezing them —
      `trusted_proxy_addr`'s exact-IP-only v1 just shipped and may want
      room to change if CIDR ranges turn out to matter in practice.

## Process (the actual blockers today)

- [ ] **Merge all open PRs to `main`.** [#13](https://github.com/tetrachromeio/oxygen/pull/13)
      (Codec), [#14](https://github.com/tetrachromeio/oxygen/pull/14)
      (Static), [#15](https://github.com/tetrachromeio/oxygen/pull/15)
      (WS), [#16](https://github.com/tetrachromeio/oxygen/pull/16) (Test),
      [#17](https://github.com/tetrachromeio/oxygen/pull/17) (trusted-proxy)
      are open and reviewed-but-unmerged. Nothing is 1.0 while half of
      what's "shipped" isn't actually on the branch people install from.
- [ ] Close the stale issues their PRs already answer
      ([#5](https://github.com/tetrachromeio/oxygen/issues/5),
      [#6](https://github.com/tetrachromeio/oxygen/issues/6),
      [#7](https://github.com/tetrachromeio/oxygen/issues/7) are still open
      despite #13/#14/#15 covering them).
- [ ] Fix the merge-mangled heading in `CHANGELOG.md` (a truncated line
      from the Router/Middleware merge, right before the `Oxygen.Router`
      entry) so the changelog reads as one document before it's the
      changelog for a tagged release.
- [ ] Tag `v1.0.0` once the above is done. First actual release; no
      pre-1.0 tags exist yet to compare against.

## Testing / CI

- [ ] **Run `examples/selftest` and every module's self-test in CI**
      (GitHub Actions) on every PR. Right now "ran it manually before
      opening the PR" is the only thing catching a regression, and that's
      exactly the kind of gap that caused the two follow-up security
      review rounds already in this repo's history — CI doesn't forget to
      run the test.
- [ ] **Move the 18-check security-regression suite into the repo** (it's
      currently a scratchpad script, not committed anywhere) as a real
      test under `examples/`, run in CI alongside selftest. It's the thing
      that's actually caught every security bug found so far; it
      shouldn't live somewhere that gets wiped when a session ends.

## Security

- [x] Two rounds of adversarial review already done (see CHANGELOG), each
      turning up real issues (smuggling, header injection, DoS) that got
      fixed.
- [ ] One more adversarial pass right before tagging, covering everything
      merged since the last round (the module PRs, trusted-proxy) —
      relying on prior rounds covering code that didn't exist yet isn't
      good enough.
- [ ] Exercise `SECURITY.md`'s reporting process at least once before 1.0
      (even a dry run) — it's never actually been used.

## Performance

- [ ] Re-measure the README's speed numbers right before tagging — several
      core files (`parse.h2`, `loop.h2`) have changed since those numbers
      were taken, and citing stale numbers in a 1.0 README is worse than
      not having numbers.
- [ ] Publish the benchmark kit (`wrk` scripts, the Rust/Node/Python
      comparison servers) that produced those numbers, or stop citing
      numbers nobody outside this repo can reproduce. Either is fine; the
      current "not published yet" isn't, for a 1.0.

## Found along the way: real gaps, not process

- [ ] **Runtime-configurable core limits.** `MAX_BODY_BYTES`, `MAX_HEADERS`,
      and `MAX_HEADER_BYTES` (`limits.h2`) are compile-time constants —
      everything else operationally important (`OXYGEN_IDLE_TIMEOUT_SECONDS`,
      `OXYGEN_HEADER_TIMEOUT_SECONDS`) is already env-var overridable so a
      deployment can tune it without a rebuild. A 1.0 server that needs a
      recompile to accept a bigger upload is a real operational gap, not
      a nice-to-have. Same pattern as the timeouts: an env var read once
      at startup, not per-request.
- [ ] **Document the crash contract.** Hydrogen's checked arithmetic traps
      (`SIGILL`) on overflow, in anyone's handler code, with no recover/
      unwind mechanism — confirmed in `h2rt.c`, there's no signal handler
      for it beyond `SIGTERM`/`SIGINT`/`SIGPIPE`. That means **one
      handler bug crashes the whole process**, not just the connection
      that triggered it — every thread, every other connection, gone.
      Given the "no runtime underneath" design, in-process recovery from
      a trap mid-execution isn't realistically safe to build (no
      exceptions, no GC, state left who-knows-where). The honest 1.0 fix
      isn't code, it's documentation: state this plainly in the README's
      **Limits** section and recommend the actual production answer (a
      process supervisor — `systemd` `Restart=always`, a container
      orchestrator's restart policy, or equivalent) as part of deploying
      Oxygen, not an afterthought discovered the hard way.
- [ ] **Decide on compression, explicitly.** There's no response gzip/br
      today. Given the "no allocation per request" core design, building
      it into the core is the wrong move — but staying silent about it
      is also wrong (TLS gets an explicit "put this behind a proxy" line
      in the README; compression doesn't, it's just absent). Recommend
      the same treatment: an explicit README line saying compression is a
      proxy's job (nginx/Caddy/etc. already do this well in front of any
      backend), not a silently missing feature.

## Explicit non-goals (say so, don't just leave them out)

- [x] TLS — already documented ("put Oxygen behind a proxy for HTTPS").
- [ ] Per-IP/connection-count rate limiting — already documented as "a
      proxy/OS job," carry this into the 1.0 README unchanged.
- [ ] HTTP/2 and HTTP/3 — not currently mentioned anywhere; add an
      explicit line once compression's is added, same reasoning (a
      front-end proxy already speaks these and downgrades to HTTP/1.1,
      which is exactly this project's design point).

## Tracking

Each unchecked item above should become its own issue (or reuse an existing
one) before work starts on it, following this repo's usual pattern — this
file is the map, not the work itself.
