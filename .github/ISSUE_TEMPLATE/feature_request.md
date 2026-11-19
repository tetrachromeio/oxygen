---
name: Feature request
about: Propose an addition or change to Oxygen's API
title: ""
labels: enhancement
---

### What's missing, and why

What are you trying to build, and what does Oxygen not let you do today?

### Proposed API

Sketch the shape you have in mind (new function/method, new field, etc.).

### How it fits Oxygen's design

Oxygen's design is: no allocation per request, no runtime underneath (no
async executor, no GC, no interpreter), one event loop per core with no
locks on the request path. Say how your proposal keeps that — or if it
can't, why the trade-off is worth it anyway.

### Alternatives considered

Can this be built on top of the existing API (e.g. in your own handler)
instead of inside Oxygen?
