# Security Policy

## Supported versions

Oxygen is pre-1.0 and tracks `main`. Security fixes land there; there's no
older branch getting backports yet.

| Version | Supported |
|---|---|
| `main` | ✅ |

## Reporting a vulnerability

**Please don't open a public issue for a security problem.**

Use GitHub's private reporting instead: go to the **Security** tab of this
repository → **Report a vulnerability**, or open one directly at
<https://github.com/tetrachromeio/oxygen/security/advisories/new>. That opens
a private draft advisory only the maintainers can see, so the issue isn't
public before there's a fix.

Please include:
- What the issue is and why it matters (what a successful exploit gets an
  attacker, and against what kind of deployment).
- Steps to reproduce it, ideally a minimal handler plus the exact
  request(s)/bytes that trigger it. A small standalone client script is
  ideal, since this is socket-level parsing code.
- The commit or version you tested against.

### What to expect

- An acknowledgement, generally within a few days.
- We'll confirm the issue, work out a fix, and credit you in the advisory
  and the fix's commit/changelog entry, unless you'd rather stay anonymous.
- Once a fix is out, the advisory is published with the details.

### Scope

In scope: `init.h2` itself — request parsing (headers, chunked bodies,
pipelining), response writing, and the event loop's handling of connections.
Memory-safety and correctness bugs there (crashes, memory corruption,
response splitting/injection, data leaking between unrelated connections,
unbounded resource growth from a single client) are all worth reporting.

Out of scope (known, documented limitations rather than bugs — see the
README's **Limits** section): no TLS (Oxygen is meant to sit behind a
TLS-terminating proxy), no idle-connection timeout yet, and no built-in
per-IP or connection-count limiting (that's a job for a proxy or the OS, not
this framework). Denial of service from simply opening many connections or
sending traffic faster than the hardware can handle isn't an Oxygen bug;
denial of service from a *small* amount of client input causing
*disproportionate* server-side cost (memory, CPU, or hung connections) is.
