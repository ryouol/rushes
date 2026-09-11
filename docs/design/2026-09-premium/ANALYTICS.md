# Optional analytics integration

Status: implemented locally and tested without network access. No measurement ID is supplied or configured, so no analytics script loads and no consent banner is displayed. This implementation is not an operator approval or a claim of legal compliance.

## Integration

The root server layout already wraps its content in `AnalyticsProvider` from `@/components/analytics-consent` and passes the server-configured `RUSHES_GA_MEASUREMENT_ID`. The provider accepts optional `measurementId?: string | null` and required `children: ReactNode`. Leave the environment variable unset until operator decisions are complete. Only trimmed IDs matching `G-` plus ten uppercase letters/digits are accepted; no sample ID is wired into the application. `AnalyticsChoices({ className?: string })` opens an accessible preferences dialog. `useAnalyticsConsent()` supplies `configured`, `choice` and `openPreferences`; settings uses these values rather than claiming analytics is always disabled.

The existing `track()` API accepts only `workspace_created`, `project_created` and `export_started`, with runtime allowlisting and no payload argument. The existing real export-start call is connected. A public CTA click is not mapped to these completion events: clicking Start a project does not prove a project was created.

## Consent and data handling

This uses a basic opt-in approach: no third-party script is inserted before an affirmative choice (including an affirmative choice previously stored for that measurement ID). Storage failure retains denied defaults and still permits a choice for the current page. The configured banner offers equally styled Accept and Decline controls; preferences can be reopened later. Cross-tab storage changes update the active choice.

Google documents setting defaults before measurement commands, persisting the visitor’s choice, and applying later consent updates. This adapter defaults analytics and advertising consent to denied and grants only analytics storage after acceptance. [Google consent setup](https://developers.google.com/tag-platform/security/guides/consent).

The adapter disables default page views, Google signals and advertising personalization. Revocation first sets Google’s documented per-property disable flag, stops the RUSHES adapter, removes queued events and its script element, sends a denied update, and expires only the integration’s prefixed cookies. Removing a script element cannot undo already executed code or recall already sent data; the disable flag prevents future property collection. [Google privacy controls](https://developers.google.com/tag-platform/security/guides/privacy).

App-provided event fields contain only an allowed event name, destination measurement ID, fixed `RUSHES` title, empty referrer, and sanitized origin plus a known route. All `/app/...` paths collapse to `/app`; unknown paths collapse to `/`. Query strings, fragments, private route IDs, names, filenames, notes and search text never enter this adapter. The script request uses `no-referrer`. Google’s own tag can create browser/client identifiers and process device/network information after consent; this is not an identifier-free or anonymous analytics claim. The documented location/title/referrer overrides are used explicitly. [Google configuration reference](https://developers.google.com/analytics/devguides/collection/ga4/reference/config).

## Operator requirements before enabling

Disable all Enhanced Measurement events in the GA4 web stream, including history-based page views, scroll, outbound clicks, site search, video, file downloads and form interactions. Review the Google tag’s automatic event-detection settings and connected destinations. These settings can collect page/form/media data outside the RUSHES `track()` allowlist and cannot be comprehensively verified or controlled by this client adapter. Enabling the measurement ID requires a real admin and browser-network audit of those settings; the isolated tests do not validate a Google account. [Google Enhanced Measurement settings](https://support.google.com/analytics/answer/9216061).

The operator must supply and approve:

- `<!-- TODO: provide analytics measurement ID -->`
- `<!-- TODO: provide analytics provider, measurement ID, and tracking decision -->`
- `<!-- TODO: provide applicable analytics consent requirements and approved cookie copy -->`

The candidate provider is GA4. The provider decision, retention/consent requirements, reviewed banner copy and public privacy disclosures remain operator work. No live configuration, network tag request, account change or deployment occurred here.

## Focused verification

`cd web && node --test lib/analytics.test.cjs` passes six isolated tests with script insertion recorded in a fake DOM, never executed. They cover malformed/missing IDs; no tag before acceptance; denied-first configuration; allowlisted events and private-data exclusion; revocation, queue/script/cookie cleanup and blocked future events; per-ID storage, storage restrictions and cross-tab revocation; and blocked tag-loading behavior that cannot interrupt product actions. `npm run typecheck` also passes. In-app browser inspection of the configured banner/dialog layout, keyboard focus/return, equal actions and settings/footer integration remains separate from those tests. Live-provider verification remains pending until the operator supplies an approved real configuration.
