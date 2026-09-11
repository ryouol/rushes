export type SafeEvent =
  "workspace_created" | "project_created" | "export_started";
export type AnalyticsChoice = "accepted" | "declined" | null;
type Adapter = { send: (event: SafeEvent) => void };
const events = new Set([
  "workspace_created",
  "project_created",
  "export_started",
]);
let configured: Adapter | null = null;
let consent = false;
export function configureAnalytics(adapter: Adapter | null) {
  configured = adapter;
}
export function setAnalyticsConsent(allowed: boolean) {
  consent = allowed;
}
export function track(event: SafeEvent) {
  if (consent && configured && events.has(event)) {
    try {
      configured.send(event);
    } catch {
      /* Telemetry must never interrupt product actions. */
    }
  }
}

/* <!-- TODO: provide analytics measurement ID -->
 * <!-- TODO: provide analytics provider, measurement ID, and tracking decision -->
 * <!-- TODO: provide applicable analytics consent requirements and approved cookie copy -->
 * Before enabling GA4, disable Enhanced Measurement and automatic event detection
 * in the Google tag's admin settings. See docs/design/2026-09-premium/ANALYTICS.md.
 */
export function analyticsMeasurementId(value?: string | null) {
  const id = value?.trim();
  return id && /^G-[A-Z0-9]{10}$/.test(id) ? id : null;
}
declare global {
  interface Window {
    rushesDataLayer?: IArguments[];
    [key: `ga-disable-${string}`]: boolean | undefined;
  }
}
const denied = {
  analytics_storage: "denied",
  ad_storage: "denied",
  ad_user_data: "denied",
  ad_personalization: "denied",
};
const publicRoutes = new Set([
  "/",
  "/login",
  "/signup",
  "/onboarding",
  "/privacy",
  "/terms",
  "/contact",
]);
function safePage() {
  const path = window.location.pathname;
  const route = publicRoutes.has(path)
    ? path
    : path === "/app" || path.startsWith("/app/")
      ? "/app"
      : "/";
  return {
    page_location: window.location.origin + route,
    page_referrer: "",
    page_title: "RUSHES",
  };
}

export function createAnalyticsController(
  value?: string | null,
  onChoiceChange?: (choice: AnalyticsChoice) => void,
) {
  const id = analyticsMeasurementId(value);
  const host = window;
  const key = `rushes.analytics.${id}.v1`;
  const cookiePrefix = `rushes_${id?.replace("-", "").toLowerCase()}`;
  let choice: AnalyticsChoice = null;
  let script: HTMLScriptElement | null = null;
  let initialized = false;
  let disposed = false;
  function command(..._args: unknown[]) {
    host.rushesDataLayer?.push(arguments);
  }
  function disable() {
    setAnalyticsConsent(false);
    configureAnalytics(null);
    if (!id) return;
    host[`ga-disable-${id}`] = true;
    if (initialized) {
      host.rushesDataLayer?.splice(0);
      command("consent", "update", denied);
    }
    if (script) {
      script.onerror = null;
      script.remove();
    }
    script = null;
    try {
      for (const cookie of document.cookie.split(";")) {
        const name = cookie.split("=")[0].trim();
        if (!name.startsWith(`${cookiePrefix}_`)) continue;
        document.cookie = `${name}=; Max-Age=0; Path=/`;
        document.cookie = `${name}=; Max-Age=0; Path=/; Domain=${window.location.hostname}`;
      }
    } catch {
      /* Browser cookie restrictions must not prevent revocation. */
    }
  }
  function apply(next: AnalyticsChoice) {
    choice = next;
    if (!id || next !== "accepted") {
      disable();
      return;
    }
    host[`ga-disable-${id}`] = false;
    host.rushesDataLayer ||= [];
    command("consent", "default", denied);
    command("consent", "update", { ...denied, analytics_storage: "granted" });
    command("set", {
      ...safePage(),
      send_page_view: false,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      ads_data_redaction: true,
      url_passthrough: false,
    });
    command("js", new Date());
    command("config", id, {
      ...safePage(),
      send_page_view: false,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_prefix: cookiePrefix,
      cookie_domain: window.location.hostname,
      cookie_path: "/",
      ignore_referrer: true,
    });
    initialized = true;
    if (!script) {
      try {
        script = document.createElement("script");
        script.async = true;
        script.referrerPolicy = "no-referrer";
        script.onerror = disable;
        script.src = `https://www.googletagmanager.com/gtag/js?id=${id}&l=rushesDataLayer`;
        document.head.appendChild(script);
      } catch {
        disable();
        return;
      }
    }
    configureAnalytics({
      send: (event) => {
        if (!disposed && choice === "accepted" && events.has(event))
          command("event", event, { ...safePage(), send_to: id });
      },
    });
    setAnalyticsConsent(true);
  }
  function storageChanged(event: StorageEvent) {
    if (event.key !== key && event.key !== null) return;
    const next =
      event.newValue === "accepted" || event.newValue === "declined"
        ? event.newValue
        : null;
    if (next === choice) return;
    apply(next);
    onChoiceChange?.(next);
  }
  if (id) {
    try {
      const saved = localStorage.getItem(key);
      choice = saved === "accepted" || saved === "declined" ? saved : null;
    } catch {
      /* Storage restrictions keep the default denied state. */
    }
  }
  apply(choice);
  if (id) window.addEventListener("storage", storageChanged);
  return {
    configured: !!id,
    get choice() {
      return choice;
    },
    choose(next: Exclude<AnalyticsChoice, null>) {
      if (disposed || !id || next === choice) return;
      try {
        localStorage.setItem(key, next);
      } catch {
        /* Choice remains valid for this page. */
      }
      apply(next);
    },
    dispose() {
      disposed = true;
      window.removeEventListener("storage", storageChanged);
      disable();
    },
  };
}
