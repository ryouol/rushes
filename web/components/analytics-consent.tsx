"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Dialog } from "@/components/dialog";
import {
  createAnalyticsController,
  type AnalyticsChoice,
} from "@/lib/analytics";
import "./analytics-consent.css";

const AnalyticsContext = createContext({
  configured: false,
  choice: null as AnalyticsChoice,
  openPreferences: () => {},
});
export function useAnalyticsConsent() {
  return useContext(AnalyticsContext);
}

export function AnalyticsProvider({
  measurementId,
  children,
}: {
  measurementId?: string | null;
  children: ReactNode;
}) {
  const controller = useRef<ReturnType<
    typeof createAnalyticsController
  > | null>(null);
  const [state, setState] = useState({
    configured: false,
    choice: null as AnalyticsChoice,
  });
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const current = createAnalyticsController(measurementId, (choice) =>
      setState((previous) => ({ ...previous, choice })),
    );
    controller.current = current;
    setState({ configured: current.configured, choice: current.choice });
    return () => {
      current.dispose();
      controller.current = null;
    };
  }, [measurementId]);
  function choose(choice: "accepted" | "declined") {
    controller.current?.choose(choice);
    setState((previous) => ({ ...previous, choice }));
    setOpen(false);
    setNotice(
      choice === "accepted"
        ? "Optional analytics allowed in this browser."
        : "Optional analytics declined. Future RUSHES analytics events are disabled.",
    );
  }
  const controls = (
    <div className="analytics-actions">
      <button className="secondary" onClick={() => choose("declined")}>
        Decline analytics
      </button>
      <button className="secondary" onClick={() => choose("accepted")}>
        Accept analytics
      </button>
    </div>
  );
  return (
    <AnalyticsContext.Provider
      value={{ ...state, openPreferences: () => setOpen(true) }}
    >
      {children}
      {state.configured && state.choice === null && !open && (
        <section
          className="analytics-banner"
          aria-label="Optional analytics preferences"
        >
          <div>
            <h2>Optional analytics</h2>
            <p>
              Allow Google Analytics to measure project creation and exports
              using cookies? You can decline and keep using RUSHES. Change your
              choice anytime in Analytics choices.{" "}
              <a href="/privacy">Privacy details</a>
            </p>
          </div>
          {controls}
        </section>
      )}
      <p className="sr-only" role="status">
        {notice}
      </p>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Analytics choices"
        description={
          state.configured
            ? "Choose whether this browser allows optional Google Analytics. Essential sign-in cookies are separate."
            : "Optional analytics are not configured on this instance. No analytics script is loaded by RUSHES."
        }
      >
        {state.configured && (
          <div className="stack">
            <p>
              Current choice:{" "}
              {state.choice === "accepted"
                ? "Allowed"
                : state.choice === "declined"
                  ? "Declined"
                  : "Not chosen"}
              .
            </p>
            <p className="small muted">
              Declining stops future events from this integration and clears its
              analytics cookies. It does not delete data already sent to Google.
            </p>
            {controls}
          </div>
        )}
      </Dialog>
    </AnalyticsContext.Provider>
  );
}

export function AnalyticsChoices({
  className = "text-button",
}: {
  className?: string;
}) {
  const { openPreferences } = useAnalyticsConsent();
  return (
    <button type="button" className={className} onClick={openPreferences}>
      Analytics choices
    </button>
  );
}
