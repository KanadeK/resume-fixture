# Design, acceptance and review boundaries

User: a developer implementing resumable downloads. Acceptance: an actual interrupted
socket response followed by a conditional resume reconstructs the original hash; after
the entity changes, a 200 replacement reconstructs v2 and blind append does not.

`server.py` generates slices from a repeated SHA-256-derived pattern, computes expected
representation digests in bounded chunks, and owns four independent scenario states.
A lock selects the representation and claims a first-full-GET fault atomically. Socket
writing occurs outside the lock. HEAD and 304 responses do not mutate scenario state.
`demo.py` is an intentionally small reference client, not a production downloader.

The basis is [RFC 9110 range request semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-range-requests).
Only strong ETags are modeled for If-Range. Date conditions fall back to 200 because no
Last-Modified model is offered. A malformed/multipart range can be ignored. HEAD ignores
Range. Single valid ranges clamp an oversized end; nonoverlapping ranges return 416.

Threat boundaries: no input-file access, shell execution, credentials or upstream client.
The server accepts local connections only; it is not a public HTTP deployment target.
Local clients are not isolated from one another. Payloads are at most 64 MiB, chunked in
64 KiB writes. Counters are fixed in number. Request headers are not copied into responses
or logs. Standard-library HTTP parser limits and a five-second socket timeout apply.

Tests include parser boundaries, exact byte slices, conditional ordering, simultaneous
drop claims, short-body exceptions, changed-content hashes, no-fault HEAD probes, 416,
unknown paths, CLI validation, and the end-to-end demo. CI additionally installs and runs
the distribution. This is not exhaustive HTTP conformance testing.
