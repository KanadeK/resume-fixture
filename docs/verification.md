# Release verification

Version: 0.1.0. Local platform: Windows, CPython 3.13.16.

- 22 regression tests cover range parsing, exact generated slices, condition ordering,
  short responses, safe reassembly, entity changes, concurrent fault claims, HEAD/416,
  paths/methods and the CLI.
- Four real-socket demo checks pass and compare complete representation SHA-256 values.
- Ruff lint and formatting checks pass. The lab's development dependency audit found no
  known vulnerabilities at verification time; runtime package dependencies are empty.
- A source distribution and a wheel are built; the wheel is installed without dependencies
  in a fresh virtual environment outside the checkout, where tests and the console demo run.
- GitHub CI runs the same functional suite and package smoke flow on Ubuntu/Windows with
  Python 3.11 and 3.13. The release process requires all four jobs to pass.

Second-pass review checked the actual safety scenario, rather than only status codes:
the changed representation's old prefix must not be appended to the new complete body.
It also checked that concurrent requests claim only one drop, probes do not accidentally
consume the fault, ranges cannot trigger file access, counters cannot grow per URL, and
response writes do not hold the scenario lock. Limitations are documented in README.

No claim is made about all HTTP clients or RFC conformance outside the supported subset.
