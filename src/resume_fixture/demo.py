"""Executable reference-client demonstrations using actual loopback sockets."""

import hashlib
import http.client

from .server import running_fixture


def exchange(server, path, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        complete = True
        try:
            body = response.read()
        except http.client.IncompleteRead as error:
            body, complete = error.partial, False
        return response.status, dict(response.getheaders()), body, complete
    finally:
        connection.close()


def run_demo():
    results = []
    with running_fixture() as server:
        split = server.size // 3
        a = exchange(server, "/stable.bin", {"Range": f"bytes=0-{split - 1}"})
        b = exchange(server, "/stable.bin", {"Range": f"bytes={split}-"})
        results.append(
            {
                "scenario": "stable-ranges",
                "passed": a[0] == b[0] == 206
                and hashlib.sha256(a[2] + b[2]).hexdigest() == server.hashes[1],
            }
        )
        for path, expected_version in (("/drop-once.bin", 1), ("/changed.bin", 2)):
            first = exchange(server, path)
            second = exchange(
                server, path, {"Range": f"bytes={len(first[2])}-", "If-Range": first[1]["ETag"]}
            )
            # A 200 response replaces the partial representation; a 206 appends.
            assembled = first[2] + second[2] if second[0] == 206 else second[2]
            results.append(
                {
                    "scenario": path[1:-4],
                    "passed": not first[3]
                    and second[3]
                    and len(first[2]) == server.drop_after
                    and second[0] == (206 if expected_version == 1 else 200)
                    and hashlib.sha256(assembled).hexdigest() == server.hashes[expected_version],
                    "resume_status": second[0],
                }
            )
        ignored = exchange(server, "/ignore-range.bin", {"Range": "bytes=20-"})
        results.append(
            {
                "scenario": "ignored-range",
                "passed": ignored[0] == 200 and len(ignored[2]) == server.size and ignored[3],
            }
        )
    return {"schema_version": 1, "passed": all(r["passed"] for r in results), "checks": results}
