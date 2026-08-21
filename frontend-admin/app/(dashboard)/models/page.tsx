"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Model } from "@/lib/types";
import {
  Badge,
  Button,
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
  Textarea,
  Toggle,
} from "@/components/ui";
import { fmtMoney, fmtNumber } from "@/lib/format";

interface Form {
  public_id: string;
  display_name: string;
  upstream_model: string;
  provider: string;
  description: string;
  context_window: string;
  max_output_tokens: string;
  aliases: string;
  input_price_per_1m: string;
  output_price_per_1m: string;
  supports_streaming: boolean;
  is_default: boolean;
  enabled: boolean;
}

const EMPTY: Form = {
  public_id: "",
  display_name: "",
  upstream_model: "",
  provider: "openai",
  description: "",
  context_window: "8192",
  max_output_tokens: "",
  aliases: "",
  input_price_per_1m: "0",
  output_price_per_1m: "0",
  supports_streaming: true,
  is_default: false,
  enabled: true,
};

function toForm(m: Model): Form {
  return {
    public_id: m.public_id,
    display_name: m.display_name,
    upstream_model: m.upstream_model,
    provider: m.provider,
    description: m.description,
    context_window: String(m.context_window),
    max_output_tokens: m.max_output_tokens != null ? String(m.max_output_tokens) : "",
    aliases: m.aliases.join(", "),
    input_price_per_1m: String(m.input_price_per_1m),
    output_price_per_1m: String(m.output_price_per_1m),
    supports_streaming: m.supports_streaming,
    is_default: m.is_default,
    enabled: m.enabled,
  };
}

export default function ModelsPage() {
  const { data: models, error, loading, reload } = useApi(() => api.listModels(), []);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Model | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [rowBusy, setRowBusy] = useState<string | null>(null);

  function set<K extends keyof Form>(k: K, v: Form[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setFormError(null);
    setOpen(true);
  }

  function openEdit(m: Model) {
    setEditing(m);
    setForm(toForm(m));
    setFormError(null);
    setOpen(true);
  }

  async function submit() {
    setBusy(true);
    setFormError(null);
    const aliases = form.aliases
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const payload = {
      display_name: form.display_name,
      upstream_model: form.upstream_model,
      provider: form.provider,
      description: form.description,
      context_window: Number(form.context_window) || 8192,
      max_output_tokens: form.max_output_tokens ? Number(form.max_output_tokens) : null,
      aliases,
      input_price_per_1m: Number(form.input_price_per_1m) || 0,
      output_price_per_1m: Number(form.output_price_per_1m) || 0,
      supports_streaming: form.supports_streaming,
      is_default: form.is_default,
      enabled: form.enabled,
    };
    try {
      if (editing) {
        await api.updateModel(editing.id, payload);
      } else {
        await api.createModel({ ...payload, public_id: form.public_id });
      }
      setOpen(false);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to save model.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleEnabled(m: Model) {
    setRowBusy(m.id);
    try {
      await api.updateModel(m.id, { enabled: !m.enabled });
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  async function remove(m: Model) {
    if (!confirm(`Delete model "${m.public_id}"?`)) return;
    setRowBusy(m.id);
    try {
      await api.deleteModel(m.id);
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Models"
        description="Map public model IDs to upstream models and set pricing."
        actions={
          <Button variant="primary" onClick={openCreate}>
            Add model
          </Button>
        }
      />

      <ErrorBox message={error} />

      {loading && !models ? (
        <Loading />
      ) : !models || models.length === 0 ? (
        <EmptyState
          title="No models registered"
          hint="Add a model to expose it on /v1/models and route requests upstream."
          action={
            <Button variant="primary" onClick={openCreate}>
              Add model
            </Button>
          }
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Model</Th>
              <Th>Upstream</Th>
              <Th className="text-right">Context</Th>
              <Th className="text-right">In / Out ($/1M)</Th>
              <Th>Enabled</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.id}>
                <Td>
                  <div className="flex items-center gap-2 font-medium text-sand-50">
                    {m.display_name}
                    {m.is_default && <Badge tone="bright">default</Badge>}
                  </div>
                  <div className="font-mono text-xs text-sand-500">{m.public_id}</div>
                  {m.aliases.length > 0 && (
                    <div className="mt-0.5 text-xs text-sand-500">
                      aka {m.aliases.join(", ")}
                    </div>
                  )}
                </Td>
                <Td className="text-sand-200">{m.upstream_model}</Td>
                <Td className="text-right">{fmtNumber(m.context_window)}</Td>
                <Td className="text-right">
                  {fmtMoney(m.input_price_per_1m)} / {fmtMoney(m.output_price_per_1m)}
                </Td>
                <Td>
                  <Toggle
                    checked={m.enabled}
                    disabled={rowBusy === m.id}
                    onChange={() => toggleEnabled(m)}
                  />
                </Td>
                <Td>
                  <div className="flex justify-end gap-1.5">
                    <Button size="sm" onClick={() => openEdit(m)}>
                      Edit
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => remove(m)}>
                      Delete
                    </Button>
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `Edit ${editing.public_id}` : "Add model"}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={busy} onClick={submit}>
              {editing ? "Save" : "Create"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Public ID" hint="What clients send as `model`.">
              <Input
                value={form.public_id}
                disabled={!!editing}
                onChange={(e) => set("public_id", e.target.value)}
                placeholder="gpt-4o"
              />
            </Field>
            <Field label="Display name">
              <Input
                value={form.display_name}
                onChange={(e) => set("display_name", e.target.value)}
                placeholder="GPT-4o"
              />
            </Field>
            <Field label="Upstream model">
              <Input
                value={form.upstream_model}
                onChange={(e) => set("upstream_model", e.target.value)}
                placeholder="gpt-4o"
              />
            </Field>
            <Field label="Provider">
              <Select value={form.provider} onChange={(e) => set("provider", e.target.value)}>
                <option value="openai">openai</option>
                <option value="anthropic">anthropic</option>
                <option value="notrack">notrack</option>
              </Select>
            </Field>
            <Field label="Context window">
              <Input
                type="number"
                value={form.context_window}
                onChange={(e) => set("context_window", e.target.value)}
              />
            </Field>
            <Field label="Max output tokens">
              <Input
                type="number"
                value={form.max_output_tokens}
                onChange={(e) => set("max_output_tokens", e.target.value)}
                placeholder="optional"
              />
            </Field>
            <Field label="Input $/1M">
              <Input
                type="number"
                step="0.01"
                value={form.input_price_per_1m}
                onChange={(e) => set("input_price_per_1m", e.target.value)}
              />
            </Field>
            <Field label="Output $/1M">
              <Input
                type="number"
                step="0.01"
                value={form.output_price_per_1m}
                onChange={(e) => set("output_price_per_1m", e.target.value)}
              />
            </Field>
          </div>

          <Field label="Aliases" hint="Comma-separated, e.g. default, gpt-4">
            <Input value={form.aliases} onChange={(e) => set("aliases", e.target.value)} />
          </Field>

          <Field label="Description">
            <Textarea
              rows={2}
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </Field>

          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm text-sand-200">
              <Toggle checked={form.enabled} onChange={(v) => set("enabled", v)} /> Enabled
            </label>
            <label className="flex items-center gap-2 text-sm text-sand-200">
              <Toggle
                checked={form.supports_streaming}
                onChange={(v) => set("supports_streaming", v)}
              />{" "}
              Streaming
            </label>
            <label className="flex items-center gap-2 text-sm text-sand-200">
              <Toggle checked={form.is_default} onChange={(v) => set("is_default", v)} /> Default
            </label>
          </div>

          <ErrorBox message={formError} />
        </div>
      </Modal>
    </div>
  );
}
