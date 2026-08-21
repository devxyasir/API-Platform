"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Plan } from "@/lib/types";
import {
  Badge,
  Button,
  ConfirmModal,
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
  Toggle,
} from "@/components/ui";
import { fmtMoney, fmtNumber } from "@/lib/format";

export default function PlansPage() {
  const [includeArchived, setIncludeArchived] = useState(false);
  const { data, error, loading, reload } = useApi(
    () => api.listPlans({ include_archived: includeArchived }),
    [includeArchived],
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [archiving, setArchiving] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);

  async function confirmArchive() {
    if (!archiving) return;
    setBusy(true);
    try {
      await api.archivePlan(archiving.id);
      setArchiving(null);
      reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Plans"
        description="Pricing tiers — their fees, included credits, limits, features and model access."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New plan
          </Button>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <Toggle checked={includeArchived} onChange={setIncludeArchived} />
        <span className="text-sm text-sand-200">Show archived</span>
      </div>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No plans" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Plan</Th>
              <Th className="text-right">Monthly</Th>
              <Th className="text-right">Yearly</Th>
              <Th className="text-right">Credits/mo</Th>
              <Th className="text-right">Trial</Th>
              <Th>Visibility</Th>
              <Th>Status</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id}>
                <Td>
                  <div className="font-medium text-sand-50">{p.name}</div>
                  <div className="font-mono text-xs text-sand-500">{p.slug}</div>
                </Td>
                <Td className="text-right">{fmtMoney(p.price_monthly_usd)}</Td>
                <Td className="text-right">{fmtMoney(p.price_yearly_usd)}</Td>
                <Td className="text-right">{fmtNumber(p.monthly_credits)}</Td>
                <Td className="text-right text-sand-200">{p.trial_days ? `${p.trial_days}d` : "—"}</Td>
                <Td>
                  <Badge tone={p.is_public ? "sand" : "olive"}>
                    {p.is_public ? "public" : "private"}
                  </Badge>
                </Td>
                <Td>
                  <Badge tone={p.archived ? "olive" : p.active ? "bright" : "sand"}>
                    {p.archived ? "archived" : p.active ? "active" : "inactive"}
                  </Badge>
                </Td>
                <Td>
                  <div className="flex justify-end gap-1.5">
                    <Link href={`/plans/${p.id}`} className="btn-ghost !px-2.5 !py-1.5 !text-xs">
                      Edit
                    </Link>
                    {!p.archived && (
                      <Button size="sm" variant="danger" onClick={() => setArchiving(p)}>
                        Archive
                      </Button>
                    )}
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {createOpen && (
        <CreatePlanModal
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            reload();
          }}
        />
      )}
      <ConfirmModal
        open={!!archiving}
        title="Archive plan"
        message={`Archive "${archiving?.name}"? It will stay attached to existing subscriptions but can no longer be assigned to new ones.`}
        confirmLabel="Archive"
        destructive
        busy={busy}
        onConfirm={confirmArchive}
        onClose={() => setArchiving(null)}
      />
    </div>
  );
}

function CreatePlanModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [monthly, setMonthly] = useState("0");
  const [yearly, setYearly] = useState("0");
  const [credits, setCredits] = useState("0");
  const [trial, setTrial] = useState("0");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.createPlan({
        slug: slug.trim(),
        name: name.trim(),
        description: description.trim(),
        price_monthly_usd: Number(monthly) || 0,
        price_yearly_usd: Number(yearly) || 0,
        monthly_credits: Number(credits) || 0,
        trial_days: Number(trial) || 0,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to create plan.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="New plan"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Create
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Slug" hint="Unique identifier.">
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="pro" />
          </Field>
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Pro" />
          </Field>
        </div>
        <Field label="Description">
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Price / month (USD)">
            <Input type="number" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
          </Field>
          <Field label="Price / year (USD)">
            <Input type="number" value={yearly} onChange={(e) => setYearly(e.target.value)} />
          </Field>
          <Field label="Included credits / month">
            <Input type="number" value={credits} onChange={(e) => setCredits(e.target.value)} />
          </Field>
          <Field label="Trial days">
            <Input type="number" value={trial} onChange={(e) => setTrial(e.target.value)} />
          </Field>
        </div>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
