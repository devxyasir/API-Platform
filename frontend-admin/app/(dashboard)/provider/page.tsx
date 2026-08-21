"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { HealthCheckResult, Provider } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  StatCard,
  StatusBadge,
  Toggle,
} from "@/components/ui";
import { fmtMs, fmtRelative } from "@/lib/format";
import type { ReactNode } from "react";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-sand-500/20 py-2 last:border-0">
      <span className="text-sm text-sand-500">{label}</span>
      <span className="text-right text-sm text-sand-50">{children}</span>
    </div>
  );
}

export default function ProviderPage() {
  const providers = useApi(() => api.listProviders(), []);
  const status = useApi(() => api.providerStatus(), []);

  const [editing, setEditing] = useState<Provider | null>(null);
  const [checking, setChecking] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<HealthCheckResult | null>(null);

  async function runCheck(p: Provider) {
    setChecking(p.id);
    setLastCheck(null);
    try {
      const res = await api.providerHealthCheck(p.id);
      setLastCheck(res);
      providers.reload();
    } finally {
      setChecking(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Provider"
        description="Upstream configuration is masked — the real credential lives only in the server environment."
      />

      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          {(status.data ?? []).map((s) => (
            <StatCard
              key={s.provider}
              label={`Circuit · ${s.provider}`}
              value={<StatusBadge status={s.circuit_state} />}
              sub={`${s.consecutive_failures} consecutive failures`}
            />
          ))}
          {lastCheck && (
            <StatCard
              label="Last health check"
              value={<StatusBadge status={lastCheck.healthy ? "healthy" : "unhealthy"} />}
              sub={lastCheck.latency_ms != null ? fmtMs(lastCheck.latency_ms) : ""}
            />
          )}
        </div>

        <ErrorBox message={providers.error} />

        {providers.loading && !providers.data ? (
          <Loading />
        ) : !providers.data || providers.data.length === 0 ? (
          <Card>
            <p className="py-6 text-center text-sm text-sand-500">
              No provider configured. Set the upstream key in the server environment.
            </p>
          </Card>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {providers.data.map((p) => (
              <Card
                key={p.id}
                title={p.name}
                actions={
                  <div className="flex items-center gap-2">
                    <Badge tone={p.enabled ? "bright" : "olive"}>
                      {p.enabled ? "enabled" : "disabled"}
                    </Badge>
                    <StatusBadge status={p.last_status} />
                  </div>
                }
              >
                <Row label="Type">{p.provider_type}</Row>
                <Row label="Base URL">{p.base_url}</Row>
                <Row label="Auth mode">{p.auth_mode}</Row>
                <Row label="Credential">
                  <code className="text-sand-200">{p.key_masked || "—"}</code>
                </Row>
                <Row label="Timeout">{p.timeout}s</Row>
                <Row label="Max retries">{p.max_retries}</Row>
                <Row label="Last checked">{fmtRelative(p.last_checked_at)}</Row>
                <Row label="Last latency">
                  {p.last_latency_ms != null ? fmtMs(p.last_latency_ms) : "—"}
                </Row>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => setEditing(p)}>
                    Settings
                  </Button>
                  <Button size="sm" loading={checking === p.id} onClick={() => runCheck(p)}>
                    Run health check
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {editing && (
        <SettingsModal
          provider={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            providers.reload();
          }}
        />
      )}
    </div>
  );
}

function SettingsModal({
  provider,
  onClose,
  onSaved,
}: {
  provider: Provider;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [enabled, setEnabled] = useState(provider.enabled);
  const [timeoutS, setTimeoutS] = useState(String(provider.timeout));
  const [maxRetries, setMaxRetries] = useState(String(provider.max_retries));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.updateProvider(provider.id, {
        enabled,
        timeout: Number(timeoutS),
        max_retries: Number(maxRetries),
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to update provider.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`${provider.name} settings`}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <label className="flex items-center gap-2 text-sm text-sand-200">
          <Toggle checked={enabled} onChange={setEnabled} /> Enabled
        </label>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Timeout (seconds)">
            <Input
              type="number"
              step="0.5"
              value={timeoutS}
              onChange={(e) => setTimeoutS(e.target.value)}
            />
          </Field>
          <Field label="Max retries">
            <Input
              type="number"
              value={maxRetries}
              onChange={(e) => setMaxRetries(e.target.value)}
            />
          </Field>
        </div>
        <p className="text-xs text-sand-500">
          The API credential can only be changed via the server environment — it is never editable
          or visible here.
        </p>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
