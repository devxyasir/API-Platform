"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Project } from "@/lib/types";
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
  Table,
  Td,
  Th,
  Textarea,
  Toggle,
} from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";

interface Form {
  owner_id: string;
  name: string;
  description: string;
  rpm_limit: string;
  tpm_limit: string;
  concurrency_limit: string;
  monthly_token_quota: string;
  allowed_models: string;
  archived: boolean;
}

const EMPTY: Form = {
  owner_id: "",
  name: "",
  description: "",
  rpm_limit: "",
  tpm_limit: "",
  concurrency_limit: "",
  monthly_token_quota: "",
  allowed_models: "",
  archived: false,
};

const numOrNull = (s: string) => (s.trim() ? Number(s) : null);

export default function ProjectsPage() {
  const { data: projects, error, loading, reload } = useApi(() => api.listProjects(), []);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
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

  function openEdit(p: Project) {
    setEditing(p);
    setForm({
      owner_id: p.owner_id,
      name: p.name,
      description: p.description,
      rpm_limit: p.rpm_limit != null ? String(p.rpm_limit) : "",
      tpm_limit: p.tpm_limit != null ? String(p.tpm_limit) : "",
      concurrency_limit: p.concurrency_limit != null ? String(p.concurrency_limit) : "",
      monthly_token_quota: p.monthly_token_quota != null ? String(p.monthly_token_quota) : "",
      allowed_models: p.allowed_models.join(", "),
      archived: p.archived,
    });
    setFormError(null);
    setOpen(true);
  }

  async function submit() {
    setBusy(true);
    setFormError(null);
    const payload = {
      name: form.name.trim(),
      description: form.description,
      rpm_limit: numOrNull(form.rpm_limit),
      tpm_limit: numOrNull(form.tpm_limit),
      concurrency_limit: numOrNull(form.concurrency_limit),
      monthly_token_quota: numOrNull(form.monthly_token_quota),
      allowed_models: form.allowed_models
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      archived: form.archived,
    };
    try {
      if (editing) await api.updateProject(editing.id, payload);
      else await api.createProject(form.owner_id.trim(), payload);
      setOpen(false);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to save project.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(p: Project) {
    if (!confirm(`Delete project "${p.name}"?`)) return;
    setRowBusy(p.id);
    try {
      await api.deleteProject(p.id);
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Projects"
        description="Group keys and set shared limits and model allow-lists."
        actions={
          <Button variant="primary" onClick={openCreate}>
            New project
          </Button>
        }
      />

      <ErrorBox message={error} />

      {loading && !projects ? (
        <Loading />
      ) : !projects || projects.length === 0 ? (
        <EmptyState
          title="No projects yet"
          hint="Projects let you scope limits and allowed models to a set of keys."
          action={
            <Button variant="primary" onClick={openCreate}>
              New project
            </Button>
          }
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th className="text-right">RPM</Th>
              <Th className="text-right">TPM</Th>
              <Th className="text-right">Monthly quota</Th>
              <Th>Status</Th>
              <Th>Created</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <Td>
                  <div className="font-medium text-sand-50">{p.name}</div>
                  {p.description && (
                    <div className="text-xs text-sand-500">{p.description}</div>
                  )}
                </Td>
                <Td className="text-right">{p.rpm_limit ?? "—"}</Td>
                <Td className="text-right">{p.tpm_limit ?? "—"}</Td>
                <Td className="text-right">
                  {p.monthly_token_quota != null ? fmtNumber(p.monthly_token_quota) : "—"}
                </Td>
                <Td>
                  <Badge tone={p.archived ? "olive" : "bright"}>
                    {p.archived ? "archived" : "active"}
                  </Badge>
                </Td>
                <Td className="text-sand-200">{fmtDate(p.created_at)}</Td>
                <Td>
                  <div className="flex justify-end gap-1.5">
                    <Button size="sm" onClick={() => openEdit(p)}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      loading={rowBusy === p.id}
                      onClick={() => remove(p)}
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

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `Edit ${editing.name}` : "New project"}
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
          {!editing && (
            <Field label="Owner user id" hint="The user who will own this project.">
              <Input
                value={form.owner_id}
                onChange={(e) => set("owner_id", e.target.value)}
                placeholder="usr_…"
              />
            </Field>
          )}
          <Field label="Name">
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Description">
            <Textarea
              rows={2}
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="RPM limit">
              <Input
                type="number"
                value={form.rpm_limit}
                onChange={(e) => set("rpm_limit", e.target.value)}
                placeholder="none"
              />
            </Field>
            <Field label="TPM limit">
              <Input
                type="number"
                value={form.tpm_limit}
                onChange={(e) => set("tpm_limit", e.target.value)}
                placeholder="none"
              />
            </Field>
            <Field label="Concurrency">
              <Input
                type="number"
                value={form.concurrency_limit}
                onChange={(e) => set("concurrency_limit", e.target.value)}
                placeholder="none"
              />
            </Field>
            <Field label="Monthly token quota">
              <Input
                type="number"
                value={form.monthly_token_quota}
                onChange={(e) => set("monthly_token_quota", e.target.value)}
                placeholder="none"
              />
            </Field>
          </div>
          <Field label="Allowed models" hint="Comma-separated. Empty = all models.">
            <Input
              value={form.allowed_models}
              onChange={(e) => set("allowed_models", e.target.value)}
              placeholder="gpt-4o, gpt-4o-mini"
            />
          </Field>
          {editing && (
            <label className="flex items-center gap-2 text-sm text-sand-200">
              <Toggle checked={form.archived} onChange={(v) => set("archived", v)} /> Archived
            </label>
          )}
          <ErrorBox message={formError} />
        </div>
      </Modal>
    </div>
  );
}
