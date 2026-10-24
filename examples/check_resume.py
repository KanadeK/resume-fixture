"""Run the built-in socket demonstration without starting a persistent server."""

import json

from resume_fixture.demo import run_demo

report = run_demo()
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
