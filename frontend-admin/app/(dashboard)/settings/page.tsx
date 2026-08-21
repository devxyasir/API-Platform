"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, API_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  Field,
  Input,
  PageHeader,
} from "@/components/ui";
import type { ReactNode } from "react";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-sand-500/20 py-3 last:border-0">
      <span className="text-sm text-sand-500">{label}</span>
      <span className="text-right text-sm text-sand-50">{children}</span>
    </div>
  );
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function changePassword() {
    setErr(null);
    setOk(false);
    if (next !== confirm) {
      setErr("New passwords do not match.");
      return;
    }
    if (next.length < 8) {
      setErr("New password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setOk(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to change password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Settings" description="Your account and connection details." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Account">
          <Row label="Name">{user?.name || "—"}</Row>
          <Row label="Email">{user?.email}</Row>
          <Row label="Role">
            <Badge tone={user?.role === "admin" ? "bright" : "olive"}>{user?.role}</Badge>
          </Row>
          <Row label="Plan">
            <span className="capitalize">{user?.plan}</span>
          </Row>
          <Row label="Status">
            <Badge tone="bright">{user?.status}</Badge>
          </Row>
          <div className="mt-4">
            <Button
              variant="danger"
              onClick={() => {
                logout();
                router.replace("/login");
              }}
            >
              Sign out
            </Button>
          </div>
        </Card>

        <Card title="Change password">
          <div className="space-y-4">
            <Field label="Current password">
              <Input
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                autoComplete="current-password"
              />
            </Field>
            <Field label="New password">
              <Input
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                autoComplete="new-password"
              />
            </Field>
            <Field label="Confirm new password">
              <Input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
            </Field>
            <ErrorBox message={err} />
            {ok && (
              <div className="rounded-lg border border-sand-50/35 bg-sand-50/10 px-3 py-2 text-sm text-sand-50">
                Password updated.
              </div>
            )}
            <Button variant="primary" loading={busy} onClick={changePassword}>
              Update password
            </Button>
          </div>
        </Card>

        <Card title="Connection" className="lg:col-span-2">
          <Row label="API base URL">
            <code className="text-sand-200">{API_BASE}</code>
          </Row>
          <Row label="OpenAI-compatible endpoint">
            <code className="text-sand-200">{API_BASE}/v1</code>
          </Row>
          <Row label="Anthropic-compatible endpoint">
            <code className="text-sand-200">{API_BASE}/v1/messages</code>
          </Row>
          <p className="mt-3 text-xs text-sand-500">
            Point your OpenAI or Anthropic SDK at the base URL above and authenticate with a key
            from the API Keys page.
          </p>
        </Card>
      </div>
    </div>
  );
}
