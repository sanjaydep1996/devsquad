---
field: Security
owners: apex, alpha_be, gamma_qa, delta_devops
---
## Store passwords properly
tags: password, login, auth, hash
when: login, password, sign up, account, auth
decide: Hash passwords with a slow salted hash (Argon2id, bcrypt or PBKDF2), never encrypt or store them, and rate-limit login attempts.

## Authorise every request
tags: authorization, access control, idor, permission
when: user, account, admin, team, invite, own, profile
decide: Check on the server that the current user may act on this exact record; never trust ids or roles sent by the client.

## Never build queries or commands from strings
tags: injection, sql, command, xss
when: query, search, filter, shell, html, template
decide: Use parameterised queries, argument lists for commands, and output escaping for HTML.

## Treat tokens as secrets
tags: token, session, jwt, cookie, link
when: token, session, invite, reset, link, email
decide: Make tokens long and random, short-lived, single-use where possible, and stored hashed; send them only over HTTPS.

## Least privilege everywhere
tags: permissions, secrets, least privilege
when: service account, key, deploy, admin, cloud
decide: Give each service and person only the access they need, and rotate keys that were ever exposed.
