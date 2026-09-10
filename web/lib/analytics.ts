/** Future analytics adapter. No identifiers, network calls, or nonessential cookies by default. */
type SafeEvent = "workspace_created" | "project_created" | "export_started";
type Adapter = { send: (event: SafeEvent) => void };
let configured: Adapter | null = null;
let consent = false;
export function configureAnalytics(adapter: Adapter | null) {
  configured = adapter;
}
export function setAnalyticsConsent(allowed: boolean) {
  consent = allowed;
}
export function track(event: SafeEvent) {
  if (consent && configured) configured.send(event);
}
