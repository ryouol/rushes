# Google sign-in

RUSHES supports Google account creation, returning sign-in, and explicit connection of Google to an existing password account. The backend uses the existing RUSHES database session strategy and HttpOnly session cookie. A new Google account does not inherit any workspace; onboarding creates its own workspace through the existing authenticated API.

## Provider configuration

Configure a **Web application** OAuth client in Google Auth Platform for RUSHES. Register these exact redirect URIs for the corresponding deployments:

- Local: `http://localhost:3741/api/auth/google/callback`
- Hosted: `https://rushes.onrender.com/api/auth/google/callback`

The backend derives its callback URI from `RUSHES_ORIGIN`; it never derives it from a browser-supplied host or return URL. A different origin or port needs its own matching registered redirect URI. Store `RUSHES_GOOGLE_CLIENT_ID` and `RUSHES_GOOGLE_CLIENT_SECRET` in the server environment. Local development can use the ignored `.env`; hosted deployment must use its environment secret settings. The client secret is represented as `SecretStr`, never exposed by the provider availability endpoint, and never placed in a browser authorization URL.

Configure consent branding, support contact, audience, and any testing-account restrictions for the RUSHES project. Only `openid email profile` scopes are requested. No Google Drive, Gmail, media-library, offline access, or refresh-token permission is requested. Google's [web server flow documentation](https://developers.google.com/identity/protocols/oauth2/web-server) describes the provider setup and exact redirect matching.

Wayline was inspected read-only as a reference. Its implementation is under `lingbot_map/workspace/auth_routes.py` and `identity.py` in `/Users/royluo/Documents/Codex/2026-08-31/turn-this-into-a-workable-prompt-2/work/lingbot-map`. Its `render.yaml` declares `WAYLINE_GOOGLE_CLIENT_ID` and `WAYLINE_GOOGLE_CLIENT_SECRET` as server environment settings. No Wayline credential value was read, copied, or committed for this implementation. RUSHES has its own configuration and identity records.

## Identity and session handling

The authorization request includes random state, nonce, and an S256 PKCE challenge. A short-lived database attempt holds only hashed state/browser binding, nonce, PKCE verifier, destination, expiry, and an optional initiating-session reference for explicit linking. Its browser cookie is HttpOnly, SameSite=Lax, scoped to `/api/auth/google`, and Secure on HTTPS. Attempts expire after 10 minutes, are bounded across the instance, and are atomically consumed before a provider exchange. Starting a newer attempt in the same browser replaces that browser's flow cookie.

Google's official `google-auth` verifier checks the signed ID token, issuer, audience, issue time, and expiry using Google's certificates. RUSHES additionally checks the nonce, authorized party when present, verified email flag, subject, and email format. Google documents the stable subject identifier and identity-token requirements in its [OpenID Connect guide](https://developers.google.com/identity/openid-connect/openid-connect); the verification library is documented in [`google.oauth2.id_token`](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html).

Persistent `google_identity` rows contain the stable Google subject, RUSHES user ID, latest verified Google email, and connection creation time. A new user receives its Google display name and verified email, plus an unguessable generated password hash. Provider access tokens, refresh tokens, raw ID tokens, and authorization codes are not retained. Existing RUSHES profile fields are not replaced when a connected Google email changes.

Matching email alone never grants access to an existing password account. The user must sign in with that account and choose **Connect Google** in Settings. This action requires the same-origin authenticated POST and binds the attempt to its initiating session. Logout deletes that session and invalidates its pending linking attempts; expiry and account activity are checked again on return. A Google identity cannot move to another user, and each RUSHES user can connect one Google identity. Disconnect and password recovery are outside this change.

Successful login uses the existing seven-day database session and SameSite=Strict session cookie. OAuth state cookies are cleared on completion. Return destinations are limited to `/app` with an optional bounded query, or `/onboarding`; external URLs, fragments, control characters, backslashes, and ambiguous duplicate inputs are rejected.

## API inventory

| Method and path | Access and result |
| --- | --- |
| `GET /api/auth/providers` | Public; `{google: boolean}` reports whether both server settings are present. |
| `GET /api/auth/google/authorize?next=…` | Public and throttled; creates a browser-bound attempt and redirects to Google. |
| `GET /api/auth/google/callback` | Public and throttled; requires valid one-time state and browser binding before exchanging a code. |
| `GET /api/auth/google/account` | Active session; `{available, connected, email}` for the current user only. |
| `POST /api/auth/google/link` | Active session and allowed Origin; returns `{authorization_url}` and sets the flow cookie. |

The callback redirects sign-in errors to `/login?error=` with an allowlisted `google_cancelled`, `google_unavailable`, `google_invalid`, `google_failed`, or `google_link_required` code. A recognized linking attempt returns to `/app?view=settings&google=` with `linked`, `cancelled`, or `link_failed`. Missing or invalid state has no trusted linking context and uses the login error destination.

The new `google_identity` and `oauth_attempt` tables are global authentication tables, like `user` and `accesstoken`; they are deliberately excluded from tenant RLS. Their routes enforce active-user identity or browser-bound OAuth state. Workspace membership and tenant isolation remain in the existing workspace APIs. Migration `0006` creates the tables, indexes, cascading user/session references, and explicit runtime-role grants. It does not silently remove linked login methods on downgrade.

OAuth callback query parameters are removed before API access logging. The Next incoming-request logger also excludes the callback. Provider exception text is neither logged nor returned. Reverse proxies or externally configured ingress loggers must also omit callback query strings; the application cannot configure external logging services.

## Verification evidence and limits

Local migration `0006` was applied and the OAuth implementation was tested against local PostgreSQL with generated RSA-signed tokens and mocked Google HTTP. The final focused OAuth, database, and request-boundary run passed **65 tests**. The complete backend suite passed **247 tests**, with one existing skip. Tests cover successful signup and returning identity, current-user account visibility, PKCE, issuer/audience/nonce/authorized-party/signature/expiry rejection, verified-email enforcement, state replay, distinct-attempt concurrency, mixed-case password/Google registration races, logout during a suspended exchange, browser mismatch, expiration, cancellation, explicit linking, revoked or expired linking sessions, identity reassignment rejection, inactive users, safe return destinations, throttling, and callback query-log suppression. AI keys were blank for these tests; no AI or live Google calls were made by the test suite.

`scripts/verify_schema.py` also passed in an isolated disposable database: schema version `0006`, 17 forced-RLS tables, both new global authentication tables, and their cascading foreign keys. The generated test database was removed after verification. The bounded result is recorded in [fresh migration evidence](validation/fresh-migrations.json).

Provider availability means configuration is present; it is not a live provider health probe. Mocked tests do not establish successful real Google consent, correctness of deployed credentials, or hosted end-to-end behavior. Record live browser and deployment evidence separately when those checks finish.

The 11 September deployment uses a dedicated RUSHES Web client in the existing Rushes project, with an External audience published In production. Server credentials are configured locally and on Render. Production schema `0006` and the reviewed application are deployed. [Production deployment evidence](validation/production-google-deployment.json) records exact commits, deployment IDs, migration checks and live browser results.

Real Google consent and provider exchange passed. Local explicit linking and logout followed by returning Google login retained the existing workspace and projects. The production test found that accounts without a workspace could not reach connection settings; the follow-up adds account-only settings and an onboarding link without requiring a workspace. The follow-up `83d8758` is live: explicit linking succeeded on production, followed by logout, Google-only returning login, and the connected-account screen for the same existing account. No workspace or project was created for this check.

A synthetic production callback marker was absent from application logs while the callback path was present. The request-log query returned no entries and owner/service log-stream lookups returned 404. This verifies the observed application redaction only; it does not establish external ingress retention or redaction.
