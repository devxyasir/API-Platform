"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Model, Plan } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  PageHeader,
  Tabs,
  Textarea,
  Toggle,
} from "@/components/ui";

const LIMIT_METRICS = [
  { key: "rpm", label: "Requests / minute" },
  { key: "rph", label: "Requests / hour" },
  { key: "rpd", label: "Requests / day" },
  { key: "tpm", label: "Tokens / minute" },
  { key: "tpd", label: "Tokens / day" },
  { key: "concurrency", label: "Concurrent requests" },
  { key: "monthly_token_quota", label: "Monthly token quota" },
  { key: "daily_token_quota", label: "Daily token quota" },
];

export default function PlanDetailPage() {
  const params = useParams<{ id: string }>();
  const planId = params.id;
  const [tab, setTab] = useState("details");

  const { data: plan, error, loading, reload } = useApi<Plan>(() => api.getPlan(planId), [planId]);

  return (
    <div>
      <PageHeader
        title={plan?.name || "Plan"}
        description={plan?.slug}
        actions={
          <Link href="/plans" className="btn-ghost !px-3 !py-1.5 !text-xs">
            ← All plans
          </Link>
        }
      />

      <ErrorBox message={error} />

      {loading && !plan ? (
        <Loading />
      ) : !plan ? (
        <EmptyState title="Plan not found" />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <Badge tone={plan.archived ? "olive" : plan.active ? "bright" : "sand"}>
              {plan.archived ? "archived" : plan.active ? "active" : "inactive"}
            </Badge>
            <Badge tone={plan.is_public ? "sand" : "olive"}>
              {plan.is_public ? "public" : "private"}
            </Badge>
          </div>

          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "details", label: "Details" },
              { key: "limits", label: "Limits" },
              { key: "models", label: "Models" },
              { key: "features", label: "Features" },
            ]}
          />

          {tab === "details" && <DetailsTab plan={plan} onSaved={reload} />}
          {tab === "limits" && <LimitsTab plan={plan} onSaved={reload} />}
          {tab === "models" && <ModelsTab plan={plan} onSaved={reload} />}
          {tab === "features" && <FeaturesTab plan={plan} onSaved={reload} />}
        </>
      )}
    </div>
  );
}

function useSaver(planId: string, onSaved: () => void) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  async function save(body: Partial<Plan>) {
    setBusy(true);
    setErr(null);
    setOk(false);
    try {
      await api.updatePlan(planId, body);
      setOk(true);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, err, ok, save };
}

function SaveRow({ busy, ok, onSave }: { busy: boolean; ok: boolean; onSave: () => void }) {
  return (
    <div className="flex items-center gap-3">
      <Button variant="primary" loading={busy} onClick={onSave}>
        Save
      </Button>
      {ok && <span className="text-xs text-sand-500">Saved ✓</span>}
    </div>
  );
}

function DetailsTab({ plan, onSaved }: { plan: Plan; onSaved: () => void }) {
  const [name, setName] = useState(plan.name);
  const [description, setDescription] = useState(plan.description);
  const [monthly, setMonthly] = useState(String(plan.price_monthly_usd));
  const [yearly, setYearly] = useState(String(plan.price_yearly_usd));
  const [credits, setCredits] = useState(String(plan.monthly_credits));
  const [trial, setTrial] = useState(String(plan.trial_days));
  const [sort, setSort] = useState(String(plan.sort_order));
  const [isPublic, setIsPublic] = useState(plan.is_public);
  const [active, setActive] = useState(plan.active);
  const { busy, err, ok, save } = useSaver(plan.id, onSaved);

  return (
    <Card title="Details" className="max-w-xl">
      <div className="space-y-4">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
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
          <Field label="Sort order">
            <Input type="number" value={sort} onChange={(e) => setSort(e.target.value)} />
          </Field>
        </div>
        <div className="flex gap-6">
          <label className="flex items-center gap-2 text-sm text-sand-200">
            <Toggle checked={isPublic} onChange={setIsPublic} /> Public
          </label>
          <label className="flex items-center gap-2 text-sm text-sand-200">
            <Toggle checked={active} onChange={setActive} /> Active
          </label>
        </div>
        <ErrorBox message={err} />
        <SaveRow
          busy={busy}
          ok={ok}
          onSave={() =>
            save({
              name: name.trim(),
              description: description.trim(),
              price_monthly_usd: Number(monthly) || 0,
              price_yearly_usd: Number(yearly) || 0,
              monthly_credits: Number(credits) || 0,
              trial_days: Number(trial) || 0,
              sort_order: Number(sort) || 0,
              is_public: isPublic,
              active,
            })
          }
        />
      </div>
    </Card>
  );
}

function LimitsTab({ plan, onSaved }: { plan: Plan; onSaved: () => void }) {
  const [limits, setLimits] = useState<Record<string, string>>(() => {
    const src = plan.limits || {};
    const out: Record<string, string> = {};
    for (const m of LIMIT_METRICS) {
      const v = src[m.key];
      out[m.key] = v === null || v === undefined ? "" : String(v);
    }
    return out;
  });
  const { busy, err, ok, save } = useSaver(plan.id, onSaved);

  function onSave() {
    const payload: Record<string, number | null> = {};
    for (const m of LIMIT_METRICS) {
      const raw = limits[m.key]?.trim();
      payload[m.key] = raw ? Number(raw) : null;
    }
    save({ limits: payload });
  }

  return (
    <Card title="Limits" className="max-w-xl">
      <p className="mb-4 text-xs text-sand-500">
        Leave a field blank for unlimited. These are the plan defaults; per-user overrides take
        precedence.
      </p>
      <div className="grid grid-cols-2 gap-3">
        {LIMIT_METRICS.map((m) => (
          <Field key={m.key} label={m.label}>
            <Input
              type="number"
              value={limits[m.key]}
              onChange={(e) => setLimits({ ...limits, [m.key]: e.target.value })}
              placeholder="unlimited"
            />
          </Field>
        ))}
      </div>
      <div className="mt-4 space-y-4">
        <ErrorBox message={err} />
        <SaveRow busy={busy} ok={ok} onSave={onSave} />
      </div>
    </Card>
  );
}

function ModelsTab({ plan, onSaved }: { plan: Plan; onSaved: () => void }) {
  const { data: models, error, loading } = useApi<Model[]>(() => api.listModels(), []);
  const [selected, setSelected] = useState<string[]>(plan.models || []);
  const { busy, err, ok, save } = useSaver(plan.id, onSaved);

  function toggle(publicId: string) {
    setSelected((cur) =>
      cur.includes(publicId) ? cur.filter((x) => x !== publicId) : [...cur, publicId],
    );
  }

  return (
    <Card title="Model access" className="max-w-xl">
      <p className="mb-4 text-xs text-sand-500">
        Select which models this plan can use. Selecting none allows all models.
      </p>
      <ErrorBox message={error} />
      {loading && !models ? (
        <Loading />
      ) : !models || models.length === 0 ? (
        <EmptyState title="No models" />
      ) : (
        <div className="space-y-2">
          {models.map((m) => (
            <label
              key={m.id}
              className="flex cursor-pointer items-center gap-3 rounded-lg border border-sand-500/30 px-3 py-2 text-sm"
            >
              <input
                type="checkbox"
                checked={selected.includes(m.public_id)}
                onChange={() => toggle(m.public_id)}
                className="accent-sand-50"
              />
              <span className="font-medium text-sand-50">{m.display_name}</span>
              <span className="font-mono text-xs text-sand-500">{m.public_id}</span>
            </label>
          ))}
        </div>
      )}
      <div className="mt-4 space-y-4">
        <ErrorBox message={err} />
        <SaveRow busy={busy} ok={ok} onSave={() => save({ models: selected })} />
      </div>
    </Card>
  );
}

function FeaturesTab({ plan, onSaved }: { plan: Plan; onSaved: () => void }) {
  const [text, setText] = useState(() => JSON.stringify(plan.features || {}, null, 2));
  const [parseErr, setParseErr] = useState<string | null>(null);
  const { busy, err, ok, save } = useSaver(plan.id, onSaved);

  function onSave() {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(text || "{}");
    } catch {
      setParseErr("Invalid JSON.");
      return;
    }
    setParseErr(null);
    save({ features: parsed });
  }

  return (
    <Card title="Features" className="max-w-xl">
      <p className="mb-4 text-xs text-sand-500">
        Feature flags as a JSON object (e.g. <code>{`{"priority_support": true}`}</code>).
      </p>
      <Textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-4 space-y-4">
        <ErrorBox message={parseErr || err} />
        <SaveRow busy={busy} ok={ok} onSave={onSave} />
      </div>
    </Card>
  );
}
