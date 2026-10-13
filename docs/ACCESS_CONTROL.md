# Workspace access

The default `local` mode is for a single owner's machine. Compose publishes the
backend and frontend on `127.0.0.1`; the database stays inside the Compose network.
Local mode does not require a password. Do not expose it through a tunnel.

Optional `protected` mode requires an owner password before loading private
conversations, reports, downloads or API documentation. It is a single-operator
gate, not a reviewer identity service or a production security certification.

## Owner setup

The owner runs `docker compose exec backend python -m app.security.credentials`
in an interactive terminal and enters a new password twice. This prints only a
salted password hash. Copy the complete single-quoted assignment into `.env`;
preserve the quotes because the hash contains dollar signs. Do not store the
plaintext password in `.env` or in a report.

Set `AUDITOR_ACCESS_MODE=protected`. For a browser and backend both running on
loopback HTTP, explicitly set `AUDITOR_COOKIE_SECURE=false`. For remote access,
use HTTPS, keep `AUDITOR_COOKIE_SECURE=true`, and configure exact
`AUDITOR_ALLOWED_ORIGINS` and `AUDITOR_ALLOWED_HOSTS` for your own deployment.
Non-loopback HTTP origins and insecure remote cookies are rejected at startup.
Restart the backend after changing access settings. `AUDITOR_SESSION_SECONDS`
controls expiry (60–86400 seconds). Rotating the configured password hash revokes
previous sessions; reducing lifetime also shortens existing sessions.

## Scope and checks

Passwords use salted PBKDF2-SHA256 with 600,000 iterations. Session tokens are
opaque, only their digests are stored, and cookies are HttpOnly and SameSite
Strict. Protected mutations require a session-bound CSRF token and an allowed
browser origin. Sign-out revokes the server session and hides private views and
drafts in open tabs. Private responses disable caching. Failed login attempts
are limited per connection address in the current worker; this is not a
distributed rate limiter.

The access tests cover anonymous reads and writes, exports, documentation,
invalid credentials, throttling, cookie flags, CSRF, expiry, revocation, password
rotation and malformed configuration. Frontend tests cover the gate, server
errors and stale responses after expiry. Separate PostgreSQL tests check durable
session revocation. GUI evidence is kept in `output/access-validation-v1` using
a disposable synthetic password and separate database. No owner password was
created or changed by the automated validation.

This does not establish independent human-review identity, encrypted backups,
TLS configuration, production penetration testing or multi-user authorization.

References: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
