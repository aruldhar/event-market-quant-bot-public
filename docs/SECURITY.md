# Security and Secrets

## Never commit or upload

- Kalshi private keys
- API key IDs paired with private keys
- `.env` files
- Exchange credentials
- Account recovery codes
- Personal identity documents
- Raw account exports containing sensitive data

## Local secret pattern

When credentials are eventually required:

1. Copy `.env.example` to `.env`.
2. Store only local paths and identifiers in `.env`.
3. Keep private-key files outside the repository when possible.
4. Confirm `.env` and key files remain ignored before every first push.
5. Revoke and replace any credential accidentally committed or shared.

## Bot security principles

- Least privilege
- Separate demo and production credentials
- No secrets in logs
- Explicit environment selection
- Fail closed on uncertain environment or account state
- Manual kill switch

## Runtime observability rules

- Raw response bodies stay in the raw archive and must not be copied into operational events.
- Request headers must not be written to raw or runtime logs.
- Credential-like runtime context keys are redacted.
- Runtime-event and manifest exception messages must be reviewed before any authenticated phase because third-party exception text can contain unexpected context.
- A required runtime-event write failure stops collection rather than silently creating an incomplete audit trail.


## Git closeout helper security

The checkpoint-closeout helper adds repository-safety gates before any push:

- blocks `.env`, private-key/certificate formats, credential directories, runtime raw data, logs, reports, databases, and model artifacts;
- permits only narrow tracked placeholder exceptions such as `.env.example` and `.gitkeep` files;
- scans staged added lines for high-confidence private-key and common token patterns;
- refuses pre-existing staged changes;
- stages only the exact approved changed-file set;
- refuses force-push, hard reset, `git clean`, and automatic conflict resolution;
- loads closeout policy from committed `HEAD`;
- refuses to certify changes to its own safety-critical code/config/tests;
- requires explicit final push approval.

These checks reduce accidental disclosure risk but are not a substitute for secret rotation. Any credential accidentally committed or exposed must still be revoked and replaced.
