import concurrent.futures
import hashlib
import http.client
import json
import subprocess
import sys
import unittest

from resume_fixture.demo import exchange, run_demo
from resume_fixture.server import FixtureServer, data_at, digest, parse_range, running_fixture


class RangeTests(unittest.TestCase):
    def test_closed_and_clamped(self):
        self.assertEqual(parse_range("bytes=2-5", 10), (2, 5))
        self.assertEqual(parse_range("bytes=2-999", 10), (2, 9))

    def test_open_and_suffix(self):
        self.assertEqual(parse_range("bytes=2-", 10), (2, 9))
        self.assertEqual(parse_range("bytes=-3", 10), (7, 9))
        self.assertEqual(parse_range("bytes=-30", 10), (0, 9))

    def test_unsatisfiable(self):
        for header in ("bytes=10-", "bytes=-0", "bytes=20-25"):
            with self.subTest(header=header):
                self.assertEqual(parse_range(header, 10), (-1, -1))

    def test_invalid_ranges_are_ignored(self):
        for header in (
            None,
            "bytes=-",
            "bytes=5-2",
            "items=0-2",
            "bytes=0-1,3-4",
            "bytes=bad",
            "bytes=١-٢",
            "bytes=" + "1" * 300 + "-",
        ):
            with self.subTest(header=header):
                self.assertIsNone(parse_range(header, 10))

    def test_generation_offsets_and_versions(self):
        for offset in (0, 1, 31, 32, 65535):
            self.assertEqual(data_at(1, offset, 37), data_at(1, 0, offset + 37)[offset:])
        self.assertNotEqual(data_at(1, 0, 100), data_at(2, 0, 100))
        self.assertEqual(digest(123456, 1), hashlib.sha256(data_at(1, 0, 123456)).hexdigest())

    def test_config_limits(self):
        for kwargs in (
            {"size": 1},
            {"size": 67108865},
            {"drop_after": 65536},
            {"drop_after": 0},
            {"port": -1},
            {"size": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                FixtureServer(**kwargs)


class SocketTests(unittest.TestCase):
    def setUp(self):
        self.context = running_fixture(size=20000, drop_after=4097)
        self.server = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)

    def request(self, path="/stable.bin", headers=None, method="GET"):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            client.request(method, path, headers=headers or {})
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            client.close()

    def test_manifest(self):
        status, _, body = self.request("/manifest.json")
        manifest = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(manifest["size"], 20000)
        self.assertEqual(manifest["sha256"]["v1"], digest(20000, 1))

    def test_full_get(self):
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.assertEqual(hashlib.sha256(body).hexdigest(), self.server.hashes[1])

    def test_exact_range_slice(self):
        status, headers, body = self.request(headers={"Range": "bytes=319-9123"})
        self.assertEqual(status, 206)
        self.assertEqual(headers["Content-Range"], "bytes 319-9123/20000")
        self.assertEqual(body, data_at(1, 319, 8805))

    def test_head_ignores_range_without_consuming_drop(self):
        status, headers, body = self.request("/changed.bin", {"Range": "bytes=0-1"}, "HEAD")
        self.assertEqual((status, len(body)), (200, 0))
        self.assertEqual(headers["Content-Length"], "20000")
        first = exchange(self.server, "/changed.bin")
        self.assertFalse(first[3])
        self.assertEqual(len(first[2]), 4097)

    def test_stable_resume_reassembles_exactly(self):
        first = exchange(self.server, "/drop-once.bin")
        status, _, rest = self.request(
            "/drop-once.bin", {"Range": f"bytes={len(first[2])}-", "If-Range": first[1]["ETag"]}
        )
        self.assertFalse(first[3])
        self.assertEqual(status, 206)
        self.assertEqual(hashlib.sha256(first[2] + rest).hexdigest(), self.server.hashes[1])

    def test_entity_change_requires_replacement(self):
        first = exchange(self.server, "/changed.bin")
        status, headers, rest = self.request(
            "/changed.bin", {"Range": f"bytes={len(first[2])}-", "If-Range": first[1]["ETag"]}
        )
        self.assertEqual(status, 200)
        self.assertNotEqual(headers["ETag"], first[1]["ETag"])
        self.assertEqual(hashlib.sha256(rest).hexdigest(), self.server.hashes[2])
        self.assertNotEqual(hashlib.sha256(first[2] + rest).hexdigest(), self.server.hashes[2])

    def test_if_range_mismatch_weak_and_date(self):
        for validator in ('"stale"', "W/" + self.server.tags[1], "Wed, 21 Oct 2015 07:28:00 GMT"):
            with self.subTest(validator=validator):
                status, _, body = self.request(
                    headers={"Range": "bytes=10-20", "If-Range": validator}
                )
                self.assertEqual((status, len(body)), (200, 20000))

    def test_if_none_match_precedes_range(self):
        for value in (
            self.server.tags[1],
            "W/" + self.server.tags[1],
            "*",
            '"other", ' + self.server.tags[1],
        ):
            with self.subTest(value=value):
                status, _, body = self.request(
                    headers={"Range": "bytes=0-10", "If-None-Match": value}
                )
                self.assertEqual((status, body), (304, b""))

    def test_416_includes_total(self):
        status, headers, body = self.request(headers={"Range": "bytes=20000-"})
        self.assertEqual((status, body), (416, b""))
        self.assertEqual(headers["Content-Range"], "bytes */20000")

    def test_ignore_range_route(self):
        status, headers, body = self.request("/ignore-range.bin", {"Range": "bytes=0-1"})
        self.assertEqual((status, len(body)), (200, 20000))
        self.assertNotIn("Content-Range", headers)

    def test_unknown_path_and_methods(self):
        for path in ("/../../private", "/stable.bin?token=secret", "/", "/%2e%2e/"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request(method="POST")[0], 501)

    def test_range_probe_does_not_consume_first_full_get(self):
        self.assertEqual(self.request("/drop-once.bin", {"Range": "bytes=0-1"})[0], 206)
        self.assertFalse(exchange(self.server, "/drop-once.bin")[3])
        self.assertTrue(exchange(self.server, "/drop-once.bin")[3])

    def test_concurrent_drop_claim_is_atomic(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(lambda _: exchange(self.server, "/drop-once.bin"), range(6)))
        self.assertEqual(sum(not r[3] for r in replies), 1)
        self.assertEqual(sum(r[3] for r in replies), 5)
        stats = json.loads(self.request("/stats.json")[2])
        self.assertEqual(stats["/drop-once.bin"], {"gets": 6, "drops": 1})


class WorkflowTests(unittest.TestCase):
    def test_reference_demo(self):
        report = run_demo()
        self.assertTrue(report["passed"])
        self.assertEqual(len(report["checks"]), 4)

    def test_cli_demo(self):
        result = subprocess.run(
            [sys.executable, "-m", "resume_fixture", "demo"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["passed"])

    def test_cli_invalid_options(self):
        for args in (("serve", "--size", "1"), ("serve", "--port", "65536")):
            result = subprocess.run(
                [sys.executable, "-m", "resume_fixture", *args],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
