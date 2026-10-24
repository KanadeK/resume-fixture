# resume-fixture

Test whether a downloader safely resumes interrupted transfers and restarts when the
remote representation changes. Four deterministic HTTP endpoints run on `127.0.0.1`.
No input files, upstream network calls, API keys, or runtime dependencies are needed.

[中文说明](README.zh-CN.md) · [Design and limits](docs/design.md) · [MIT](LICENSE)

## Install and prove the core flow

Python 3.11+:

```sh
git clone https://github.com/KanadeK/resume-fixture.git
cd resume-fixture
python -m pip install .
resume-fixture demo
```

The demo opens real loopback connections, observes a short body, retries with `Range`
and `If-Range`, and checks the reassembled SHA-256. Its JSON reports four checks and
`"passed": true`. It also proves that a changed ETag returns 200 and requires replacing
the partial content. It writes no files. `python -m resume_fixture demo` also works.

## Test your downloader

```sh
resume-fixture serve --port 8765 --size 65536 --drop-after 4096
```

The first stdout line is JSON with the actual origin URL. Port `0` (the default) selects
a free port. Fetch `/manifest.json` for the exact size, SHA-256 values, strong ETags,
and routes. Use a separate terminal for your client. Stop the server with Ctrl+C.
Restarting the process resets the scenarios; there is no remote reset endpoint.

| Path | Behavior |
|---|---|
| `/stable.bin` | Stable v1 bytes; single byte ranges and matching strong If-Range work |
| `/drop-once.bin` | First full GET sends only `drop-after` bytes but advertises the full length; subsequent requests serve stable v1 |
| `/changed.bin` | Same initial drop, then the same-size content and strong ETag change to v2; old If-Range receives a full 200 v2 |
| `/ignore-range.bin` | Always serves the complete v1 representation with 200, ignoring Range |
| `/stats.json` | Per-scenario GET and injected-drop counts; no request headers or payload values |

HEAD and successful partial GET probes do not consume the first-full-GET fault. An
If-None-Match hit returns 304. A valid unsatisfiable range returns 416 with the total
length. Malformed, duplicate, and multipart Range headers are ignored with a full 200.
Suffix and open-ended ranges work; an end beyond the file size is clamped.

Keep the server running through the failed transfer and retry: restarting between them
rearms the fault. Only one request claims each drop, even with concurrent clients.

## Why another HTTP fixture?

[httpbin](https://github.com/postmanlabs/httpbin) is a general HTTP test service.
[PartialProbe](https://github.com/KanadeK/partialprobe) audits existing endpoints.
This server supplies repeatable, stateful faults specifically for download clients:
stable resume, changed-entity restart, and an ignored Range. It is useful for testing
the client side of problems such as [Tart's interrupted downloads](https://github.com/openai/tart/issues/1300).
The implementation and synthetic payloads are original.

## Limits and security

This is a development fixture, bound only to IPv4 loopback. It never reads or serves
files, runs commands, accepts uploads, or contacts another host. Request logging is
disabled. Each request has a five-second socket timeout. Run it only for local testing.
Other local processes can consume the once-only fault; restart for isolation.

Version 0.1.0 supports HTTP/1.1 GET/HEAD, single ranges and ETag conditions listed above.
It deliberately closes every connection. It has no TLS, HTTP/2, multipart bodies,
Last-Modified/date validator model, If-Match, rate shaping, or production-server claim.
Ignoring Range is permitted by HTTP; fault routes intentionally return incomplete bodies.
Payloads repeat a version-specific 32-byte pattern and are not random-data benchmarks.
Size is limited to 64 MiB. `drop-after` must be at least 1 and smaller than size.

Exit codes: demo `0` all checks pass, `1` a check fails; configuration/input errors `2`.
Unexpected OS failures during the demo may raise an exception for diagnosis.

## Development and cleanup

```sh
python -m pip install -e . -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m build
python -m pip uninstall resume-fixture
```

No service is installed. Stop the process and uninstall the package to clean up. Delete
your checkout/virtual environment if no longer needed. See [contribution guidance](CONTRIBUTING.md)
and [security reporting](SECURITY.md).
