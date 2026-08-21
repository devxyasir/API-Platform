"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Organization, Plan, Subscription } from "@/lib/types";
import {
  Button,
  EmptyState,
  ErrorBox,
  Field,
  Loading,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
  Toggle,
} from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";

const SUB_STATUSES = ["trialing", "active", "past_due", "paused", "cancelled", "expired"];
const PAGE = 50;

export default function SubscriptionsPage() {
  const [status, setStatus] = useState("");
  const [orgId, setOrgId] = useState("");
  const [offset, setOffset] = useState(0);

  const { data: orgs } = useApi(
    () => api.listOrganizations({ include_personal: true, limit: 200 }),
    [],
  );
  const { data: plans } = useApi(() => api.listPlans({ include_archived: true }), []);

  const { data, error, loading, reload } = useApi(
    () =>
      api.listSubscriptions({
        status: status || undefined,
        organization_id: orgId || undefined,
        limit: PAGE,
        offset,
      }),
    [status, orgId, offset],
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [changing, setChanging] = useState<Subscription | null>(null);
  const [statusFor, setStatusFor] = useState<Subscription | null>(null);
  const [cancelling, setCancelling] = useState<Subscription | null>(null);

  const orgName = (id: string) => orgs?.items.find((o) => o.id === id)?.name || id;

  return (
    <div>
      <PageHeader
        title="Subscriptions"
        description="Every organization's plan subscription, its billing period and lifecycle status."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New subscription
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label="Status">
          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
            className="w-40"
          >
            <option value="">All statuses</option>
            {SUB_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Organization">
          <Select
            value={orgId}
            onChange={(e) => {
              setOrgId(e.target.value);
              setOffset(0);
            }}
            className="w-56"
          >
            <option value="">All organizations</option>
            {orgs?.items.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No subscriptions" />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Organization</Th>
                <Th>Plan</Th>
                <Th>Status</Th>
                <Th>Period</Th>
                <Th>Trial</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((s) => (
                <tr key={s.id}>
                  <Td>
                    <div className="font-medium text-sand-50">{orgName(s.organization_id)}</div>
                    <div className="font-mono text-xs text-sand-500">{s.organization_id}</div>
                  </Td>
                  <Td className="text-sand-200">{s.plan_name || s.plan_slug || s.plan_id}</Td>
                  <Td>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge status={s.status} />
                      {s.cancel_at_period_end && (
                        <span className="text-xs text-sand-500">(ends period)</span>
                      )}
                    </div>
                  </Td>
                  <Td className="text-xs text-sand-200">
                    {fmtDate(s.current_period_start)}
                    {s.current_period_end ? ` → ${fmtDate(s.current_period_end)}` : ""}
                  </Td>
                  <Td>{s.trial_status !== "none" ? <StatusBadge status={s.trial_status} /> : "—"}</Td>
                  <Td>
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" onClick={() => setChanging(s)}>
                        Change plan
                      </Button>
                      <Button size="sm" onClick={() => setStatusFor(s)}>
                        Status
                      </Button>
                      <Button size="sm" variant="danger" onClick={() => setCancelling(s)}>
                        Cancel
                      </Button>
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="mt-4 flex items-center justify-between text-sm text-sand-200">
            <span>{fmtNumber(data.total)} subscriptions</span>
            <div className="flex gap-2">
              <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Previous
              </Button>
              <Button size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      {createOpen && (
        <CreateSubModal
          orgs={orgs?.items || []}
          plans={plans || []}
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            reload();
          }}
        />
      )}
      {changing && (
        <ChangePlanModal
          sub={changing}
          plans={plans || []}
          onClose={() => setChanging(null)}
          onSaved={() => {
            setChanging(null);
            reload();
          }}
        />
      )}
      {statusFor && (
        <StatusModal
          sub={statusFor}
          onClose={() => setStatusFor(null)}
          onSaved={() => {
            setStatusFor(null);
            reload();
          }}
        />
      )}
      {cancelling && (
        <CancelModal
          sub={cancelling}
          onClose={() => setCancelling(null)}
          onSaved={() => {
            setCancelling(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function CreateSubModal({
  orgs,
  plans,
  onClose,
  onSaved,
}: {
  orgs: Organization[];
  plans: Plan[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [organizationId, setOrganizationId] = useState("");
  const [planId, setPlanId] = useState("");
  const [trial, setTrial] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.createSubscription({
        organization_id: organizationId,
        plan_id: planId,
        trial,
        reason: reason.trim() || undefined,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to create subscription.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="New subscription"
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
        <Field label="Organization">
          <Select value={organizationId} onChange={(e) => setOrganizationId(e.target.value)}>
            <option value="">Select…</option>
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Plan">
          <Select value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">Select…</option>
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm text-sand-200">
          <Toggle checked={trial} onChange={setTrial} /> Start with trial (if the plan offers one)
        </label>
        <Field label="Reason" hint="Recorded in plan history.">
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function ChangePlanModal({
  sub,
  plans,
  onClose,
  onSaved,
}: {
  sub: Subscription;
  plans: Plan[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [planId, setPlanId] = useState(sub.plan_id);
  const [grantCredits, setGrantCredits] = useState(true);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.changeSubscriptionPlan(sub.id, {
        plan_id: planId,
        grant_credits: grantCredits,
        reason: reason.trim() || undefined,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to change plan.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Change plan"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Apply
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="New plan">
          <Select value={planId} onChange={(e) => setPlanId(e.target.value)}>
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm text-sand-200">
          <Toggle checked={grantCredits} onChange={setGrantCredits} /> Grant the new plan&apos;s
          monthly credits
        </label>
        <Field label="Reason" hint="Recorded in plan history.">
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function StatusModal({
  sub,
  onClose,
  onSaved,
}: {
  sub: Subscription;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState(sub.status);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.setSubscriptionStatus(sub.id, status);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to set status.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Set subscription status"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Apply
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Status" hint="Manually override the lifecycle status.">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {SUB_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function CancelModal({
  sub,
  onClose,
  onSaved,
}: {
  sub: Subscription;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [atPeriodEnd, setAtPeriodEnd] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.cancelSubscription(sub.id, atPeriodEnd);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to cancel.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Cancel subscription"
      footer={
        <>
          <Button onClick={onClose}>Keep it</Button>
          <Button variant="danger" loading={busy} onClick={submit}>
            Cancel subscription
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-sand-200">
          Cancel the subscription for this organization?
        </p>
        <label className="flex items-center gap-2 text-sm text-sand-200">
          <Toggle checked={atPeriodEnd} onChange={setAtPeriodEnd} /> Cancel at period end (keep
          access until {sub.current_period_end ? fmtDate(sub.current_period_end) : "the period ends"})
        </label>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
