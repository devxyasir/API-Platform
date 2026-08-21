"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Button, ErrorBox, Field, Input, Spinner } from "@/components/ui";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ApiError } from "@/lib/api";

// Admin console sign-in. This surface is LOGIN-ONLY — there is no registration here.
// The server's /admin/auth/admin-login rejects any non-admin credentials (with a deliberately
// generic message), and lib/auth additionally refuses to render the console for a non-admin
// identity, so nothing about the admin app is exposed to a normal user.
export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Already signed in -> skip the form.
  useEffect(() => {
    if (!loading && user) router.replace("/overview");
  }, [user, loading, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email, password);
      router.replace("/overview");
    } catch (err) {
      // The server returns "invalid_credentials" for both wrong passwords and non-admin
      // accounts on purpose — never reveal which. Surface a single neutral message.
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Sign-in failed.",
      );
    } finally {
      setPending(false);
    }
  }

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="text-sand-200" />
      </div>
    );
  }

  return (
    <div className="relative grid min-h-screen place-items-center p-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-sand-50 text-lg font-bold text-sand-900">
            G
          </span>
          <h1 className="text-lg font-semibold text-sand-50">Gateway Admin</h1>
          <p className="text-sm text-sand-200">Sign in to the control plane</p>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4 p-6">
          <Field label="Email">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </Field>

          <ErrorBox message={error} />

          <Button type="submit" variant="primary" loading={pending} className="w-full">
            Sign in
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-sand-500">
          Admin access only. Sign in with a platform-admin account.
        </p>
      </div>
    </div>
  );
}
