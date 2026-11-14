---
field: DevOps
owners: delta_devops
---
## Every change goes through CI
tags: ci, pipeline, build, lint, test
when: release, deploy, pipeline, ci, merge
decide: Run lint, tests and a build on every pull request; block merges on red.

## Small, reversible releases
tags: deploy, release, rollback, feature flag
when: deploy, release, launch, migrate
decide: Ship small changes behind flags where risky, keep a one-step rollback, and deploy database migrations before the code that needs them.

## Build once, configure per environment
tags: docker, container, image, environment, twelve-factor
when: docker, container, deploy, environment, kubernetes, cloud
decide: Build one immutable image, run it as a non-root user, and inject config per environment.

## Conventional commits and clear PRs
tags: git, commit, branch, pull request
when: commit, branch, pr, release
decide: Use short-lived branches named for the change, conventional commit messages, and PR descriptions that say what, why and how to test.

## Observe what you run
tags: monitoring, health check, metrics, alert
when: deploy, service, production, uptime
decide: Expose a health check, track error rate and latency, and alert on symptoms users feel.
