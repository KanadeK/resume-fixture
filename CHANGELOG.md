# Changelog

## 0.1.0 — 2026-10-24

- Four local download scenarios with deterministic versioned content and strong ETags.
- Single-range, HEAD, If-None-Match and If-Range behavior, bounded payloads and socket timeout.
- Once-only truncation with atomic concurrent claims; changed-entity fallback to 200.
- A real-socket, digest-verified reference-client demonstration and regression tests.
