# Skills

Canonical Cursor Authoring Format (skills, agents, rules, `mcp.json`) for
`dmipeck` machines.

## Language

**Unit test**:
A test that exercises one unit of behavior in-process, hermetic against every
external boundary.
_Avoid_: isolated test, hermetic test

**Integration test**:
A test that exercises code against a real external boundary.
_Avoid_: end-to-end test, system test

**External boundary**:
Any process, service, or ambient state the code depends on that the test does
not control — database, third-party API, filesystem, environment variables,
clock, network.
_Avoid_: external interface, external dependency, IO

**Test double**:
A stand-in for a real collaborator: a stub, fake, or mock.
_Avoid_: mock (as a blanket term for any double)

**Seam**:
The public boundary at which a test observes behavior.
_Avoid_: boundary, entry point
