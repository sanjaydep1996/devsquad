---
field: Backend
owners: alpha_be
---
## Validate at the edge
tags: validation, input, request, api, schema
when: api, endpoint, form, input, request, upload
decide: Validate every request against a schema at the boundary and reject with a clear 4xx message.
Never trust client input; parse into typed objects once, then pass those inward.

## Design resource-oriented APIs
tags: rest, api, http, status code, endpoint, versioning
when: api, endpoint, rest, route
decide: Use nouns for resources, the right verbs and status codes (201 create, 400 bad input, 404 missing, 409 conflict).
Keep responses consistent: the same error shape everywhere. Version only when a breaking change is unavoidable.

## Paginate and index lists
tags: list, search, pagination, index, query, performance
when: list, search, filter, history, feed, report, export
decide: Paginate every list (cursor or limit/offset), and add an index for each filter and sort column.
Unbounded queries are the most common production slowdown. Check the query plan for anything run per request.

## Use transactions for multi-step writes
tags: transaction, consistency, write, concurrency, race
when: transfer, payment, order, invite, booking, inventory
decide: Wrap related writes in one transaction and guard concurrent updates (unique constraints, row locks or version checks).
Two requests at once is the normal case, not the edge case.

## Keep secrets and config out of code
tags: config, secret, env, twelve-factor
when: key, token, secret, credential, config, environment
decide: Read config and secrets from the environment; never commit them; fail fast at startup when one is missing.

## Log for the person on call
tags: logging, observability, error, monitoring
when: error, fail, debug, monitor, log
decide: Log one structured line per request with an id, and log errors with context but without personal data or secrets.
