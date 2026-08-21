"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { ApiKeyCreated, Project } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  CopyButton,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fmtDate, fmtRelative } from "@/lib/format";

const AVAILABLE_SCOPES = [
  "chat:write",
  "chat:read",
  "models:read",
  "usage:read",
  "conversations:write",
  "conversations:read",
];
const DEFAULT_SCOPES = ["chat:write", "chat:read", "models:read", "usage:read"];

export default function ApiKeysPage() {
  const { data: keys, error, loading, reload } = useApi(() => api.listKeys(), []);
  const { data: projects } = useApi(() => api.listProjects().catch(() => [] as Project[]), []);

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(DEFAULT_SCOPES);
  const [projectId, setProjectId] = useState("");
  const [expiresInDays, setExpiresInDays] = useState("");
  const [rpm, setRpm] = useState("");
  const [tpm, setTpm] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [secret, setSecret] = useState<ApiKeyCreated | null>(null);
  const [rowBusy, setRowBusy] = useState<string | null>(null);

  function toggleScope(s: string) {
    setScopes((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  }

  function resetForm() {
    setName("");
    setScopes(DEFAULT_SCOPES);
    setProjectId("");
    setExpiresInDays("");
    setRpm("");
    setTpm("");
    setFormError(null);
  }

  async function submit() {
    setBusy(true);
    setFormError(null);
    try {
      const created = await api.createKey({
        name: name.trim() || "Default key",
        scopes,
        project_id: projectId || null,
        expires_in_days: expiresInDays ? Number(expiresInDays) : null,
        rpm_limit: rpm ? Number(rpm) : null,
        tpm_limit: tpm ? Number(tpm) : null,
      });
      setCreateOpen(false);
      resetForm();
      setSecret(created);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to create key.");
    } finally {
      setBusy(false);
    }
  }

  async function rotate(id: string) {
    setRowBusy(id);
    try {
      const created = await api.rotateKey(id);
      setSecret(created);
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  async function revoke(id: string) {
    if (!confirm("Revoke this key? Applications using it will stop working immediately.")) return;
    setRowBusy(id);
    try {
      await api.revokeKey(id);
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  async function remove(id: string) {
    if (!confirm("Permanently delete this key? This cannot be undone.")) return;
    setRowBusy(id);
    try {
      await api.deleteKey(id);
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="API Keys"
        description="Create keys for the OpenAI/Anthropic-compatible endpoints."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New key
          </Button>
        }
      />

      <ErrorBox message={error} />

      {loading && !keys ? (
        <Loading />
      ) : !keys || keys.length === 0 ? (
        <EmptyState
          title="No API keys yet"
          hint="Create your first key to start calling the gateway from your apps and IDE."
          action={
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              New key
            </Button>
          }
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Key</Th>
              <Th>Scopes</Th>
              <Th>Status</Th>
              <Th>Last used</Th>
              <Th>Created</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id}>
                <Td className="font-medium text-sand-50">{k.name}</Td>
                <Td className="font-mono text-sand-200">{k.key_prefix}…</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {k.scopes.map((s) => (
                      <Badge key={s} tone="olive">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </Td>
                <Td>
                  <StatusBadge status={k.status} />
                </Td>
                <Td className="text-sand-200">{fmtRelative(k.last_used_at)}</Td>
                <Td className="text-sand-200">{fmtDate(k.created_at)}</Td>
                <Td>
                  <div className="flex justify-end gap-1.5">
                    <Button
                      size="sm"
                      loading={rowBusy === k.id}
                      onClick={() => rotate(k.id)}
                    >
                      Rotate
                    </Button>
                    {k.status === "active" && (
                      <Button size="sm" onClick={() => revoke(k.id)}>
                        Revoke
                      </Button>
                    )}
                    <Button size="sm" variant="danger" onClick={() => remove(k.id)}>
                      Delete
                    </Button>
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {/* Create key modal */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create API key"
        footer={
          <>
            <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} onClick={submit}>
              Create
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Local dev, VS Code"
            />
          </Field>

          <div>
            <div className="label">Scopes</div>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_SCOPES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleScope(s)}
                  className={
                    scopes.includes(s)
                      ? "rounded-full border border-sand-50/40 bg-sand-50/15 px-2.5 py-1 text-xs text-sand-50"
                      : "rounded-full border border-sand-500/45 px-2.5 py-1 text-xs text-sand-500 hover:text-sand-200"
                  }
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {projects && projects.length > 0 && (
            <Field label="Project (optional)">
              <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">No project</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}

          <div className="grid grid-cols-3 gap-3">
            <Field label="Expires (days)">
              <Input
                type="number"
                min={1}
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(e.target.value)}
                placeholder="never"
              />
            </Field>
            <Field label="RPM limit">
              <Input
                type="number"
                min={1}
                value={rpm}
                onChange={(e) => setRpm(e.target.value)}
                placeholder="default"
              />
            </Field>
            <Field label="TPM limit">
              <Input
                type="number"
                min={1}
                value={tpm}
                onChange={(e) => setTpm(e.target.value)}
                placeholder="default"
              />
            </Field>
          </div>

          <ErrorBox message={formError} />
        </div>
      </Modal>

      {/* One-time secret reveal */}
      <Modal
        open={!!secret}
        onClose={() => setSecret(null)}
        title="Save your API key"
        footer={<Button variant="primary" onClick={() => setSecret(null)}>Done</Button>}
      >
        {secret && (
          <div className="space-y-3">
            <p className="text-sm text-sand-200">
              This is the only time the full key for{" "}
              <span className="font-medium text-sand-50">{secret.name}</span> will be shown. Copy
              it now and store it securely.
            </p>
            <div className="flex items-center gap-2 rounded-lg border border-sand-500/50 bg-sand-900/60 p-3">
              <code className="flex-1 break-all text-sm text-sand-50">{secret.key}</code>
              <CopyButton value={secret.key} />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
