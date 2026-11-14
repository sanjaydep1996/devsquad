---
field: Testing
owners: gamma_qa, alpha_be
---
## Test pyramid
tags: unit, integration, e2e, strategy
when: test, feature, api, bug
decide: Most tests are fast unit tests, fewer integration tests on real boundaries, and a handful of end-to-end checks on key journeys.

## Reproduce a bug before fixing it
tags: bug, regression, reproduce
when: bug, fix, broken, error, crash, regression
decide: Write a failing test that reproduces the bug first, then fix it, so it can't come back unnoticed.

## Cover the edges
tags: edge case, boundary, null, empty, error path
when: input, form, api, parse, calculate, limit
decide: For each input, test empty, smallest, largest, wrong type and the error path, not just the happy path.

## Tests must be deterministic
tags: flaky, determinism, time, random, order
when: time, date, schedule, random, async, concurrent
decide: Control time, randomness and ordering in tests; a test that sometimes fails is a bug to fix, not to retry.

## Name the behaviour
tags: naming, readability
when: test
decide: Name each test after the behaviour it proves (rejects an expired token), and assert on outcomes, not internals.
