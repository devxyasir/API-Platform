import type { Config } from "tailwindcss";

// ── "Night sands" palette ────────────────────────────────────────────────
// Only these four brand colors drive the UI:
//   #FAE8B4 cream  · #CBBD93 sand · #80775C olive-gray · #574A24 deep olive
// Each token resolves to a CSS variable holding raw RGB channels, so Tailwind
// opacity modifiers still work (rgb(var(--x) / <alpha-value>)) AND the whole
// palette can be remapped for light vs dark mode from globals.css alone.
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sand: {
          50: "rgb(var(--sand-50) / <alpha-value>)", // cream — primary text, CTA fill, brightest
          200: "rgb(var(--sand-200) / <alpha-value>)", // sand — secondary text, accents
          500: "rgb(var(--sand-500) / <alpha-value>)", // olive-gray — borders, faint text
          900: "rgb(var(--sand-900) / <alpha-value>)", // deep olive — page background
        },
        // Semantic aliases (elevated surfaces + foreground roles).
        bg: "rgb(var(--c-bg) / <alpha-value>)",
        panel: "rgb(var(--c-panel) / <alpha-value>)",
        panel2: "rgb(var(--c-panel2) / <alpha-value>)",
        border: "rgb(var(--c-border) / <alpha-value>)",
        muted: "rgb(var(--c-muted) / <alpha-value>)",
        faint: "rgb(var(--c-faint) / <alpha-value>)",
        text: "rgb(var(--c-text) / <alpha-value>)",
        brand: "rgb(var(--c-brand) / <alpha-value>)",
        accent: "rgb(var(--c-accent) / <alpha-value>)",
      },
    },
  },
  plugins: [],
};

export default config;
