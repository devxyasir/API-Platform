"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "./ui";

// Simple stroke icons (currentColor -> inherits the sand palette).
function Icon({ path }: { path: string }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <path d={path} />
    </svg>
  );
}

const ICONS = {
  overview: "M3 12l9-9 9 9M5 10v10h14V10",
  analytics: "M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6",
  requests: "M4 6h16M4 12h16M4 18h10",
  usage: "M12 3v18M5 8l7-5 7 5M5 8v8l7 5 7-5V8",
  keys: "M15 7a4 4 0 1 1-3.9 5H7v3H4v-3H2l4.1-4.1A4 4 0 0 1 15 7z",
  projects: "M3 7h6l2 2h10v10H3V7z",
  billing: "M2 8h20M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM6 15h4",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l1.5 2.6-1.7 3-3-.4-2 1.1-.9 2.9H9.1l-.9-2.9-2-1.1-3 .4-1.7-3L3 12l-1.5-2.6 1.7-3 3 .4 2-1.1L9.1 2.8h3.8l.9 2.9 2 1.1 3-.4 1.7 3z",
} as const;

interface NavItem {
  href: string;
  label: string;
  icon: keyof typeof ICONS;
}

// Only what a normal account needs: their own traffic, keys, projects and billing.
// The administrative control plane is a separate app on separate routes.
const SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Home",
    items: [{ href: "/overview", label: "Overview", icon: "overview" }],
  },
  {
    title: "Insights",
    items: [
      { href: "/analytics", label: "Analytics", icon: "analytics" },
      { href: "/requests", label: "Requests", icon: "requests" },
      { href: "/usage", label: "Usage", icon: "usage" },
    ],
  },
  {
    title: "Access",
    items: [
      { href: "/api-keys", label: "API Keys", icon: "keys" },
      { href: "/projects", label: "Projects", icon: "projects" },
    ],
  },
  {
    title: "Billing",
    items: [{ href: "/billing", label: "Billing", icon: "billing" }],
  },
];

export function Sidebar({
  mobile = false,
  onNavigate,
}: {
  mobile?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <aside
      className={cx(
        "w-60 shrink-0 flex-col border-r border-sand-500/35 bg-panel",
        mobile ? "flex" : "hidden md:flex",
      )}
    >
      <div className="flex items-center gap-2 px-5 py-5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-sand-50 text-sm font-bold text-sand-900">
          G
        </span>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-sand-50">Gateway</div>
          <div className="text-[11px] text-sand-500">Your account</div>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-6">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-sand-500">
              {section.title}
            </div>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const active =
                  pathname === item.href || pathname.startsWith(item.href + "/");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    className={cx(
                      "flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors",
                      active
                        ? "bg-sand-50/15 font-medium text-sand-50"
                        : "text-sand-200 hover:bg-sand-500/20 hover:text-sand-50",
                    )}
                  >
                    <Icon path={ICONS[item.icon]} />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <Link
        href="/settings"
        onClick={onNavigate}
        className={cx(
          "m-3 flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors",
          pathname === "/settings"
            ? "bg-sand-50/15 font-medium text-sand-50"
            : "text-sand-200 hover:bg-sand-500/20 hover:text-sand-50",
        )}
      >
        <Icon path={ICONS.settings} />
        Settings
      </Link>
    </aside>
  );
}
