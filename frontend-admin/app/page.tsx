"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Loading } from "@/components/ui";

// Entry point: bounce to the dashboard when authenticated, otherwise to login.
export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/overview" : "/login");
  }, [user, loading, router]);

  return (
    <div className="grid min-h-screen place-items-center">
      <Loading label="Starting…" />
    </div>
  );
}
