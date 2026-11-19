### What this changes and why

### Testing

- [ ] `examples/selftest` still matches the expected output (see
      [CONTRIBUTING.md](../CONTRIBUTING.md#running-the-tests))
- [ ] If this touches request parsing (headers, chunked bodies, pipelining):
      added a test case to `examples/selftest/main.h2` that would have
      failed before this change, and updated
      `hydrogen`'s `tests/oxygen/selftest.out` to match (in a paired PR
      there, or noted below for a maintainer to sync)
- [ ] If this is performance-sensitive: measured before/after (machine,
      load tool and settings, numbers) — see the README's **Speed** section

### Checklist

- [ ] Follows the style of the surrounding code (see
      [CONTRIBUTING.md](../CONTRIBUTING.md#making-a-change))
- [ ] Updated the README/docs if the public API changed
