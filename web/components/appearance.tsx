"use client";

import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Monitor, Moon, Sun } from "lucide-react";

type Appearance = "light" | "dark" | "system";
const STORAGE_KEY = "rushes.appearance";
const AppearanceContext = createContext<{
  appearance: Appearance;
  setAppearance: (value: Appearance) => void;
}>({ appearance: "light", setAppearance: () => {} });

function preference(value: string | null): Appearance {
  return value === "dark" || value === "system" ? value : "light";
}

// Runs before paint; only the explicit System choice follows the device.
export const appearanceScript = `(function(){try{var p=localStorage.getItem("${STORAGE_KEY}");document.documentElement.dataset.theme=p==="dark"||(p==="system"&&matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light"}catch(e){document.documentElement.dataset.theme="light"}})();`;

export function AppearanceProvider({ children }: { children: React.ReactNode }) {
  const [appearance, setValue] = useState<Appearance>("light");
  const [initialized, setInitialized] = useState(false);
  useEffect(() => {
    try { setValue(preference(localStorage.getItem(STORAGE_KEY))); } catch {}
    setInitialized(true);
    const synchronize = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY || event.key === null) setValue(preference(event.newValue));
    };
    window.addEventListener("storage", synchronize);
    return () => window.removeEventListener("storage", synchronize);
  }, []);
  useEffect(() => {
    if (!initialized) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme = appearance === "system" ? (query.matches ? "dark" : "light") : appearance;
    };
    apply();
    if (appearance !== "system") return;
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [appearance, initialized]);
  function setAppearance(value: Appearance) {
    setValue(value);
    try { localStorage.setItem(STORAGE_KEY, value); } catch {}
  }
  return <AppearanceContext.Provider value={{ appearance, setAppearance }}>{children}</AppearanceContext.Provider>;
}

export function AppearanceMenu({ className = "" }: { className?: string }) {
  const { appearance, setAppearance } = useContext(AppearanceContext);
  const id = useId();
  const details = useRef<HTMLDetailsElement>(null);
  const Icon = appearance === "dark" ? Moon : appearance === "system" ? Monitor : Sun;
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (details.current?.open && !details.current.contains(event.target as Node)) details.current.open = false;
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && details.current?.open) {
        event.stopPropagation();
        details.current.open = false;
        details.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  return <details className={`appearance-menu ${className}`} ref={details}>
    <summary aria-label={`Appearance: ${appearance}`}><Icon size={19} strokeWidth={1.6} /><span>{appearance[0].toUpperCase() + appearance.slice(1)}</span><ChevronDown size={14} /></summary>
    <fieldset className="appearance-options">
      <legend>Appearance</legend>
      {(["light", "dark", "system"] as const).map(value => <label key={value}>
        <input type="radio" name={id} value={value} checked={appearance === value} onChange={() => {
          setAppearance(value);
          if (details.current) { details.current.open = false; details.current.querySelector("summary")?.focus(); }
        }} />
        {value[0].toUpperCase() + value.slice(1)}
      </label>)}
    </fieldset>
  </details>;
}
