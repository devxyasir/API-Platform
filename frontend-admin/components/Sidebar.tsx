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
  models: "M12 2l8 4v12l-8 4-8-4V6l8-4zM4 6l8 4 8-4M12 10v12",
  projects: "M3 7h6l2 2h10v10H3V7z",
  users: "M16 21v-2a4 4 0 0 0-8 0v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  organizations: "M3 21h18M6 21V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v16M18 21V9h-4M9 8h2M9 12h2M9 16h2",
  plans: "M4 5a1 1 0 0 1 1-1h9l6 6v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5zM14 4v6h6",
  subscriptions: "M17 2l4 4-4 4M3 11V9a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v2a4 4 0 0 1-4 4H3",
  credits: "M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  invoices: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h6",
  security: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  risk: "M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01",
  rate: "M12 8v4l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
  provider: "M4 7h16M4 12h16M4 17h16M7 4v16",
  health: "M3 12h4l2 5 4-12 2 7h6",
  audit: "M9 12l2 2 4-4M7 3h10l3 4v14H4V7l3-4z",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l1.5 2.6-1.7 3-3-.4-2 1.1-.9 2.9H9.1l-.9-2.9-2-1.1-3 .4-1.7-3L3 12l-1.5-2.6 1.7-3 3 .4 2-1.1L9.1 2.8h3.8l.9 2.9 2 1.1 3-.4 1.7 3z",
} as const;

interface NavItem {
  href: string;
  label: string;
  icon: keyof typeof ICONS;
}

// §42 admin navigation. This is the full control plane: everything an operator can see.
// (The main user app shows only the self-service subset — this console is admins-only.)
const SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Monitor",
    items: [
      { href: "/overview", label: "Overview", icon: "overview" },
      { href: "/analytics", label: "Analytics", icon: "analytics" },
      { href: "/requests", label: "Requests", icon: "requests" },
    ],
  },
  {
    title: "Accounts",
    items: [
      { href: "/users", label: "Users", icon: "users" },
      { href: "/organizations", label: "Organizations", icon: "organizations" },
      { href: "/projects", label: "Projects", icon: "projects" },
    ],
  },
  {
    title: "Billing",
    items: [
      { href: "/plans", label: "Plans", icon: "plans" },
      { href: "/subscriptions", label: "Subscriptions", icon: "subscriptions" },
      { href: "/credits", label: "Credits", icon: "credits" },
      { href: "/invoices", label: "Invoices", icon: "invoices" },
      { href: "/usage", label: "Usage", icon: "usage" },
    ],
  },
  {
    title: "Access",
    items: [
      { href: "/api-keys", label: "API Keys", icon: "keys" },
      { href: "/models", label: "Models", icon: "models" },
      { href: "/rate-limits", label: "Rate Limits", icon: "rate" },
    ],
  },
  {
    title: "Security",
    items: [
      { href: "/security", label: "Security", icon: "security" },
      { href: "/risk", label: "Risk", icon: "risk" },
      { href: "/audit", label: "Audit Log", icon: "audit" },
    ],
  },
  {
    title: "System",
    items: [
      { href: "/provider", label: "Providers", icon: "provider" },
      { href: "/health", label: "Health", icon: "health" },
    ],
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
          <div className="text-[11px] text-sand-500">Admin console</div>
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
