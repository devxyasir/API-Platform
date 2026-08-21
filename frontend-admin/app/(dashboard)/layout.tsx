"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isPlatformAdmin, useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/Sidebar";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge, Loading } from "@/components/ui";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [drawer, setDrawer] = useState(false);

  // Guard: only a platform admin may see any of this. Anyone else (unauthenticated, or a
  // non-admin identity that somehow reached here) is bounced to login. lib/auth already
  // refuses to populate `user` for non-admins; this is the belt-and-braces second check.
  const allowed = isPlatformAdmin(user);
  useEffect(() => {
    if (!loading && !allowed) router.replace("/login");
  }, [allowed, loading, router]);

  if (loading || !allowed || !user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Loading label="Checking session…" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      {/* Mobile slide-over navigation */}
      {drawer && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div
            className="absolute inset-0 bg-sand-900/70 backdrop-blur-sm"
            onClick={() => setDrawer(false)}
          />
          <div className="relative">
            <Sidebar mobile onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-sand-500/35 bg-panel/90 px-4 py-3 backdrop-blur">
          <button
            onClick={() => setDrawer(true)}
            className="rounded-lg border border-sand-500/50 p-1.5 text-sand-200 hover:text-sand-50 md:hidden"
            aria-label="Open navigation"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
            </svg>
          </button>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="text-sm font-medium text-sand-50">{user.name || user.email}</div>
              <div className="text-xs text-sand-500">{user.email}</div>
            </div>
            <Badge tone="bright">{user.admin_role || user.role}</Badge>
            <ThemeToggle />
            <button
              onClick={() => {
                logout();
                router.replace("/login");
              }}
              className="btn-ghost !px-3 !py-1.5 !text-xs"
            >
              Sign out
            </button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
