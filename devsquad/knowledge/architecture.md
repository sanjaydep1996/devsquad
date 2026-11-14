---
field: Architecture
owners: apex
---
## Start with the simplest design that works
tags: design, architecture, service, microservice, scale, system
when: new service, new system, microservice, architecture
decide: Start as one deployable with clear modules; split into services only when a team or scaling need forces it.
A modular monolith is cheaper to build, test and change. Split along a real seam (separate data, team or scaling profile), never by guess.

## Make the boundaries explicit
tags: module, interface, contract, api, boundary, coupling
when: interface, contract, integrate, module
decide: Define the interface (inputs, outputs, errors) before the code, and keep it stable.
Depend on interfaces, not internals. A change that crosses two modules should change one contract, not five files.

## Write the decision down (ADR)
tags: adr, decision, trade-off, record
when: choose, decide, migrate, replace, switch
decide: Record significant choices as an ADR: context, decision, consequences.
Future readers need the why. One page is enough; link it from the code it affects.

## Design for failure
tags: retry, timeout, failure, resilience, queue, idempotent
when: external, third-party, payment, webhook, queue, email
decide: Give every network call a timeout, retry with backoff only idempotent work, and make handlers idempotent.
Networks fail; duplicate deliveries happen. An idempotency key turns a retry from a risk into a no-op.

## Keep data the source of truth
tags: database, schema, migration, data model, consistency
when: database, schema, table, model, store
decide: Model the data first, change it through versioned migrations, and never break existing readers in one step.
Expand, migrate, then contract: add the new shape, move readers and writers, remove the old one later.

## Estimate with ranges, slice thin
tags: estimate, plan, scope, slice, mvp
when: plan, estimate, roadmap, mvp, feature
decide: Slice work into vertical pieces that each ship value; give estimates as ranges with the main risk named.
A thin end-to-end slice surfaces integration problems early and gives a demoable result.
