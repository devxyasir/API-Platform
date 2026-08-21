"use client";

import { useEffect, useState } from "react";
import { cx } from "./ui";

type Theme = "dark" | "light";

// Sun / moon glyphs in the same stroke style as the sidebar icons.
const SUN =
  "M12 3v1.5M12 19.5V21M4.2 4.2l1.1 1.1M18.7 18.7l1.1 1.1M3 12h1.5M19.5 12H21M4.2 19.8l1.1-1.1M18.7 5.3l1.1-1.1M12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9z";
const MOON = "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z";

// Persisted theme toggle. The pre-hydration script in app/layout.tsx has
// already applied the saved choice to <html data-theme>, so on mount we simply
// read that attribute back — no flash, and this stays the single writer of the
// `gw-theme` key. Written against the same sand tokens, so it themes itself.
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const current =
      (document.documentElement.getAttribute("data-theme") as Theme) === "light"
        ? "light"
        : "dark";
    setTheme(current);
    setMounted(true);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("gw-theme", next);
    } catch {
      /* private mode / storage disabled — the toggle still works for the session */
    }
    setTheme(next);
  }

  const target = theme === "dark" ? "light" : "dark";
  // Before mount, render the dark-default icon (SUN) to match SSR and avoid a
  // hydration mismatch; correct it once we've read the real attribute.
  const showMoon = mounted && theme === "light";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${target} mode`}
      title={`Switch to ${target} mode`}
      className={cx(
        "grid h-8 w-8 place-items-center rounded-lg border border-sand-500/50 text-sand-200 transition-colors hover:border-sand-200 hover:text-sand-50",
        className,
      )}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d={showMoon ? MOON : SUN} />
      </svg>
    </button>
  );
}
