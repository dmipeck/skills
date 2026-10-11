---
name: testing
description: High-level standards for testing, Use when writing, changing, or reviewing tests
---

# Testing

Keep the unit suite hermetic and fast. Anything that needs a real external
boundary is an integration test. The distinction drives how the code is
structured, not just where the test file lives.

## Vocabulary

- **Unit test** — exercises one unit of behavior in-process. Hermetic: no
  network, database, filesystem, environment, clock, or third-party process
  beyond the test runner.
- **Integration test** — exercises the code against a real external boundary.
- **External boundary** — any process, service, or ambient state the code
  reads from or writes to that the test does not control: database,
  third-party API, filesystem, environment variables, clock, network. Not
  *external interface* or *external dependency*.
- **Test double** — a stand-in for a real collaborator: stub (canned
  answers), fake (working in-memory implementation), mock (records and
  asserts on calls).
- **Seam** — the public boundary a test observes behavior at.

## Rules

1. Anything that can be unit-tested **MUST** be unit-tested.
2. A unit test **MUST NOT** depend on an external boundary.
3. First instinct when a dependency blocks a unit test: **refactor** so the
   dependency is passed in as a value, object, or struct. Do not reach for
   the dependency — or a mock — to force the test through.
4. If refactoring is impossible, or makes no practical sense (a function whose
   whole purpose is to read from a database), do **not** unit-test it. Write
   an **integration test**.
5. Do not mock unless necessary. Prefer real collaborators passed in over
   mocking interfaces.
6. Integration tests **MUST** be opt-in wherever the ecosystem provides a
   built-in separation (Go build tags, PHPUnit groups, pytest markers, a
   dedicated command). Never invent a custom filter to fake one. Where no
   mechanism exists, the test may live in the default suite, but must be
   clearly isolated and named, and the unit suite stays hermetic and fast.
7. Integration tests run against real dependencies. **Prefer testcontainers**
   for external services.

## Doubles

A double is a last resort, allowed only for:

- nondeterminism — clock, RNG, UUIDs;
- a third-party SDK you cannot wrap;
- simulating errors at an external boundary.

Prefer architectures where collaborators are real values or objects the
caller constructs, so tests pass fixtures in and nothing needs mocking.
Hand-write fakes; avoid mock frameworks.

## Anti-patterns

- Unit test that boots a container, hits the network, or reads env vars.
- Mock-heavy test asserting on call sequences instead of behavior.
- Integration test buried in the default suite with no marker.
- Mocking a collaborator you could have passed in as a value.

## See also

- `codebase-design` — seams, deep modules, where the boundary belongs.
- `golang-testing` — Go mechanics: testify, testcontainers-go, build tags.
- `tdd` — red/green loop; these rules pick the seam and the test kind.
