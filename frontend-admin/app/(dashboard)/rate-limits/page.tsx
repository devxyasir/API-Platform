"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { RateLimitConfig } from "@/lib/types";
import {
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fmtNumber, fmtRelative, titleCase } from "@/lib/format";

const SCOPE_TYPES = ["global", "plan", "user", "project", "api_key", "model"];
const LIMIT_FIELDS: (keyof RateLimitConfig)[] = ["rpm", "rph", "rpd", "tpm", "tpd", "concurrency"];

export default function RateLimitsPage() {
  const defaults = useApi(() => api.planDefaults(), []);
  const configs = useApi(() => api.listRateConfigs(), []);
  const events = useApi(() => api.rateEvents({ limit: 100 }), []);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<RateLimitConfig | null>(null);

  const planCols = defaults.data
    ? Array.from(
        new Set(Object.values(defaults.data).flatMap((v) => Object.keys(v))),
      )
    : [];

  return (
    <div>
      <PageHeader
        title="Rate Limits"
        description="Plan defaults and per-scope overrides. Overrides win over defaults."
        actions={
          <Button
            variant="primary"
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            Add override
          </Button>
        }
      />

      <div className="space-y-6">
        <Card title="Plan defaults">
          <ErrorBox message={defaults.error} />
          {defaults.loading || !defaults.data ? (
            <Loading />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Plan</Th>
                  {planCols.map((c) => (
                    <Th key={c} className="text-right">
                      {c.toUpperCase()}
                    </Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(defaults.data).map(([plan, limits]) => (
                  <tr key={plan}>
                    <Td className="capitalize text-sand-50">{plan}</Td>
                    {planCols.map((c) => (
                      <Td key={c} className="text-right">
                        {limits[c] != null ? fmtNumber(limits[c] as number) : "—"}
                      </Td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>

        <Card title="Overrides">
          <ErrorBox message={configs.error} />
          {configs.loading && !configs.data ? (
            <Loading />
          ) : !configs.data || configs.data.length === 0 ? (
            <EmptyState title="No overrides" hint="Everything uses the plan defaults above." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Scope</Th>
                  <Th>Scope ID</Th>
                  {LIMIT_FIELDS.map((f) => (
                    <Th key={f} className="text-right">
                      {String(f).toUpperCase()}
                    </Th>
                  ))}
                  <Th />
                </tr>
              </thead>
              <tbody>
                {configs.data.map((c) => (
                  <tr key={c.id}>
                    <Td className="capitalize text-sand-50">{c.scope_type}</Td>
                    <Td className="font-mono text-xs text-sand-200">{c.scope_id || "—"}</Td>
                    {LIMIT_FIELDS.map((f) => (
                      <Td key={f} className="text-right">
                        {c[f] != null ? fmtNumber(c[f] as number) : "—"}
                      </Td>
                    ))}
                    <Td>
                      <div className="flex justify-end gap-1.5">
                        <Button
                          size="sm"
                          onClick={() => {
                            setEditing(c);
                            setOpen(true);
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={async () => {
                            if (!confirm("Delete this override?")) return;
                            await api.deleteRateConfig(c.id);
                            configs.reload();
                          }}
                        >
                          Delete
                        </Button>
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>

        <Card title="Recent throttling events">
          <ErrorBox message={events.error} />
          {events.loading && !events.data ? (
            <Loading />
          ) : !events.data || events.data.length === 0 ? (
            <EmptyState title="No throttling events" hint="Nothing has hit a limit recently." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Time</Th>
                  <Th>Limit</Th>
                  <Th>Scope</Th>
                  <Th className="text-right">Value</Th>
                  <Th>Caller</Th>
                </tr>
              </thead>
              <tbody>
                {events.data.map((e) => (
                  <tr key={e.id}>
                    <Td className="text-sand-200">{fmtRelative(e.ts)}</Td>
                    <Td className="uppercase">{e.limit_type}</Td>
                    <Td>{e.scope}</Td>
                    <Td className="text-right">{fmtNumber(e.limit_value)}</Td>
                    <Td className="font-mono text-xs text-sand-500">
                      {e.api_key_id || e.user_id || e.project_id || "—"}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>

      {open && (
        <OverrideModal
          editing={editing}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setOpen(false);
            configs.reload();
          }}
        />
      )}
    </div>
  );
}

function OverrideModal({
  editing,
  onClose,
  onSaved,
}: {
  editing: RateLimitConfig | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [scopeType, setScopeType] = useState(editing?.scope_type ?? "user");
  const [scopeId, setScopeId] = useState(editing?.scope_id ?? "");
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      LIMIT_FIELDS.map((f) => [f, editing?.[f] != null ? String(editing[f]) : ""]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    const body: Record<string, unknown> = { scope_type: scopeType, scope_id: scopeId };
    for (const f of LIMIT_FIELDS) body[f] = vals[f]?.trim() ? Number(vals[f]) : null;
    try {
      await api.upsertRateConfig(body);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save override.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? "Edit override" : "Add override"}
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
        <div className="grid grid-cols-2 gap-3">
          <Field label="Scope type">
            <Select
              value={scopeType}
              disabled={!!editing}
              onChange={(e) => setScopeType(e.target.value)}
            >
              {SCOPE_TYPES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Scope ID" hint="Blank for global; else the user/key/project ID.">
            <Input
              value={scopeId}
              disabled={!!editing || scopeType === "global"}
              onChange={(e) => setScopeId(e.target.value)}
            />
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {LIMIT_FIELDS.map((f) => (
            <Field key={f} label={titleCase(String(f))}>
              <Input
                type="number"
                value={vals[f]}
                onChange={(e) => setVals((v) => ({ ...v, [f]: e.target.value }))}
                placeholder="—"
              />
            </Field>
          ))}
        </div>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
