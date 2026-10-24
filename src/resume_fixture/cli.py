import argparse
import json
import sys
from contextlib import suppress

from . import __version__
from .demo import run_demo
from .server import FixtureServer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local fixtures for safe HTTP download resumes.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve four deterministic scenarios on 127.0.0.1")
    serve.add_argument("--port", type=int, default=0, help="port, 0 selects a free port")
    serve.add_argument("--size", type=int, default=65536, help="representation bytes (2..67108864)")
    serve.add_argument("--drop-after", type=int, default=4096, help="bytes sent before first drop")
    sub.add_parser("demo", help="run four reference-client socket checks and print JSON")
    args = parser.parse_args(argv)
    if args.command == "demo":
        result = run_demo()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["passed"] else 1
    try:
        server = FixtureServer(args.port, args.size, args.drop_after)
    except (OSError, ValueError) as error:
        print(f"resume-fixture: {error}", file=sys.stderr)
        return 2
    with server:
        print(json.dumps({"url": server.url, "manifest": "/manifest.json"}), flush=True)
        with suppress(KeyboardInterrupt):
            server.serve_forever(poll_interval=0.1)
    return 0
