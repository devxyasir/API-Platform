"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { UserDetail } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  ConfirmModal,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  StatCard,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import { fmtDate, fmtMoney, fmtNumber, fmtRelative, fmtTokens } from "@/lib/format";

const ADMIN_ROLES = ["super_admin", "admin", "support", "billing_admin", "analyst", "moderator"];
const QUOTA_METRICS = ["monthly_token_quota", "daily_token_quota"];

export default function UserDetailPage() {
  const params = useParams<{ id: string }>();
  const userId = params.id;
  const [tab, setTab] = useState("overview");

  const { data, error, loading, reload } = useApi<UserDetail>(
    () => api.userDetail(userId),
    [userId],
  );

  const user = data?.user;

  return (
    <div>
      <PageHeader
        title={user?.name || user?.email || "User"}
        description={user?.email}
        actions={
          <Link href="/users" className="btn-ghost !px-3 !py-1.5 !text-xs">
            ← All users
          </Link>
        }
      />

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || !user ? (
        <EmptyState title="User not found" />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <StatusBadge status={user.status} />
            <Badge tone={user.role === "admin" ? "bright" : "olive"}>{user.role}</Badge>
            {user.admin_role && <Badge tone="bright">{user.admin_role}</Badge>}
            <Badge tone="sand">{user.account_type}</Badge>
          </div>

          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Plan" value={data.plan_name || data.plan_slug || user.plan} />
            <StatCard label="Credit balance" value={fmtNumber(data.credit_balance ?? user.credits)} />
            <StatCard label="Projects" value={fmtNumber(data.projects_count ?? 0)} />
            <StatCard label="API keys" value={fmtNumber(data.api_keys_count ?? 0)} />
          </div>

          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "overview", label: "Overview" },
              { key: "usage", label: "Usage & quota" },
              { key: "permissions", label: "Permissions" },
              { key: "actions", label: "Actions" },
            ]}
          />

          {tab === "overview" && <OverviewTab detail={data} />}
          {tab === "usage" && <UsageTab detail={data} />}
          {tab === "permissions" && <PermissionsTab detail={data} onChanged={reload} />}
          {tab === "actions" && <ActionsTab detail={data} onChanged={reload} />}
        </>
      )}
    </div>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-sand-500/20 py-2 last:border-0">
      <span className="text-sm text-sand-500">{label}</span>
      <span className={mono ? "font-mono text-xs text-sand-200" : "text-sm text-sand-200"}>
        {value}
      </span>
    </div>
  );
}

function OverviewTab({ detail }: { detail: UserDetail }) {
  const { user, organization, subscription } = detail;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Account">
        <InfoRow label="User id" value={user.id} mono />
        <InfoRow label="Email" value={user.email} />
        <InfoRow label="Email verified" value={user.email_verified ? "Yes" : "No"} />
        <InfoRow label="Created" value={user.created_at ? fmtDate(user.created_at) : "—"} />
        <InfoRow label="Last login" value={user.last_login ? fmtRelative(user.last_login) : "Never"} />
      </Card>

      <Card title="Organization">
        {organization ? (
          <>
            <InfoRow
              label="Name"
              value={
                <Link href={`/organizations/${organization.id}`} className="hover:text-sand-50">
                  {organization.name}
                </Link>
              }
            />
            <InfoRow label="Slug" value={organization.slug} mono />
            <InfoRow label="Status" value={<StatusBadge status={organization.status} />} />
            <InfoRow label="Type" value={organization.is_personal ? "Personal" : "Team"} />
          </>
        ) : (
          <p className="py-4 text-sm text-sand-500">No organization.</p>
        )}
      </Card>

      <Card title="Subscription" className="lg:col-span-2">
        {subscription ? (
          <div className="grid gap-x-8 sm:grid-cols-2">
            <div>
              <InfoRow label="Plan" value={detail.plan_name || detail.plan_slug || subscription.plan_id} />
              <InfoRow label="Status" value={<StatusBadge status={subscription.status} />} />
              <InfoRow
                label="Trial"
                value={subscription.trial_status !== "none" ? subscription.trial_status : "—"}
              />
            </div>
            <div>
              <InfoRow label="Period start" value={fmtDate(subscription.current_period_start)} />
              <InfoRow
                label="Period end"
                value={subscription.current_period_end ? fmtDate(subscription.current_period_end) : "—"}
              />
              <InfoRow
                label="Cancels at period end"
                value={subscription.cancel_at_period_end ? "Yes" : "No"}
              />
            </div>
          </div>
        ) : (
          <p className="py-4 text-sm text-sand-500">No subscription.</p>
        )}
      </Card>
    </div>
  );
}

function UsageTab({ detail }: { detail: UserDetail }) {
  const usage = detail.usage_30d;
  const quota = detail.quota;
  return (
    <div className="space-y-6">
      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-sand-500">
          Usage (30d)
        </div>
        {usage ? (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Requests" value={fmtNumber(usage.requests)} />
            <StatCard label="Tokens" value={fmtTokens(usage.total_tokens)} />
            <StatCard label="Cost" value={fmtMoney(usage.cost_usd)} />
            <StatCard label="Credits used" value={fmtNumber(usage.credits_used)} />
          </div>
        ) : (
          <EmptyState title="No usage recorded" />
        )}
      </div>

      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-sand-500">
          Token quota
        </div>
        {quota ? (
          <Card>
            <InfoRow label="Metric" value={quota.metric} mono />
            <InfoRow label="Limit" value={quota.unlimited ? "Unlimited" : fmtNumber(quota.limit ?? 0)} />
            <InfoRow label="Used" value={fmtNumber(quota.used)} />
            <InfoRow
              label="Remaining"
              value={quota.unlimited ? "Unlimited" : fmtNumber(quota.remaining ?? 0)}
            />
            <InfoRow label="Period start" value={fmtDate(quota.period_start)} />
            {!quota.unlimited && quota.limit ? (
              <div className="mt-3">
                <div className="h-2 w-full overflow-hidden rounded-full bg-sand-500/25">
                  <div
                    className="h-full bg-sand-50"
                    style={{
                      width: `${Math.min(100, Math.round((quota.used / quota.limit) * 100))}%`,
                    }}
                  />
                </div>
              </div>
            ) : null}
          </Card>
        ) : (
          <EmptyState title="No quota configured" hint="This user is on an unlimited plan." />
        )}
      </div>
    </div>
  );
}

function PermissionsTab({ detail, onChanged }: { detail: UserDetail; onChanged: () => void }) {
  const perms = detail.effective_permissions || [];
  const [roleOpen, setRoleOpen] = useState(false);

  return (
    <div className="space-y-4">
      <Card
        title="Admin role"
        actions={
          <Button size="sm" onClick={() => setRoleOpen(true)}>
            Change
          </Button>
        }
      >
        {detail.user.admin_role ? (
          <div className="flex items-center gap-2">
            <Badge tone="bright">{detail.user.admin_role}</Badge>
            <span className="text-xs text-sand-500">
              Grants access to the admin control plane.
            </span>
          </div>
        ) : (
          <p className="text-sm text-sand-500">
            Not an administrator. This user can only use the customer dashboard.
          </p>
        )}
      </Card>

      <Card title="Effective permissions">
        {perms.length === 0 ? (
          <p className="text-sm text-sand-500">No admin permissions.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {perms.map((p) => (
              <span
                key={p}
                className="rounded-md border border-sand-500/40 px-2 py-0.5 font-mono text-xs text-sand-200"
              >
                {p}
              </span>
            ))}
          </div>
        )}
      </Card>

      {roleOpen && (
        <AdminRoleModal
          detail={detail}
          onClose={() => setRoleOpen(false)}
          onSaved={() => {
            setRoleOpen(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function AdminRoleModal({
  detail,
  onClose,
  onSaved,
}: {
  detail: UserDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [role, setRole] = useState(detail.user.admin_role || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.setAdminRole(detail.user.id, { admin_role: role || null });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to set admin role.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Change admin role"
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
        <Field label="Admin role" hint="Leave as “None” to revoke all admin access.">
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">None (not an admin)</option>
            {ADMIN_ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

type Lifecycle = "suspend" | "unsuspend" | "disable" | "restrict";

function ActionsTab({ detail, onChanged }: { detail: UserDetail; onChanged: () => void }) {
  const { user } = detail;
  const [lifecycle, setLifecycle] = useState<Lifecycle | null>(null);
  const [creditsOpen, setCreditsOpen] = useState(false);
  const [quotaOpen, setQuotaOpen] = useState(false);
  const [revokeOpen, setRevokeOpen] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirmRevoke() {
    setRevoking(true);
    setErr(null);
    try {
      await api.revokeAllKeys(user.id);
      setRevokeOpen(false);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to revoke keys.");
    } finally {
      setRevoking(false);
    }
  }

  const isActive = user.status === "active";
  const isSuspended = user.status === "suspended";

  return (
    <div className="space-y-4">
      <ErrorBox message={err} />

      <Card title="Account status">
        <p className="mb-3 text-sm text-sand-500">
          Current status: <StatusBadge status={user.status} />
        </p>
        <div className="flex flex-wrap gap-2">
          {!isSuspended && (
            <Button onClick={() => setLifecycle("suspend")}>Suspend</Button>
          )}
          {isSuspended && (
            <Button variant="primary" onClick={() => setLifecycle("unsuspend")}>
              Unsuspend
            </Button>
          )}
          {isActive && <Button onClick={() => setLifecycle("restrict")}>Restrict</Button>}
          <Button variant="danger" onClick={() => setLifecycle("disable")}>
            Disable
          </Button>
        </div>
      </Card>

      <Card title="Credits & quota">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setCreditsOpen(true)}>Grant credits</Button>
          <Button onClick={() => setQuotaOpen(true)}>Reset quota</Button>
        </div>
      </Card>

      <Card title="API keys">
        <div className="flex flex-wrap gap-2">
          <Button variant="danger" onClick={() => setRevokeOpen(true)}>
            Revoke all keys
          </Button>
        </div>
      </Card>

      {lifecycle && (
        <LifecycleModal
          userId={user.id}
          action={lifecycle}
          onClose={() => setLifecycle(null)}
          onSaved={() => {
            setLifecycle(null);
            onChanged();
          }}
        />
      )}
      {creditsOpen && (
        <GrantCreditsModal
          userId={user.id}
          onClose={() => setCreditsOpen(false)}
          onSaved={() => {
            setCreditsOpen(false);
            onChanged();
          }}
        />
      )}
      {quotaOpen && (
        <QuotaResetModal
          userId={user.id}
          onClose={() => setQuotaOpen(false)}
          onSaved={() => {
            setQuotaOpen(false);
            onChanged();
          }}
        />
      )}
      <ConfirmModal
        open={revokeOpen}
        title="Revoke all API keys"
        message="Revoke every API key belonging to this user? Existing integrations will stop working immediately."
        confirmLabel="Revoke all"
        destructive
        busy={revoking}
        onConfirm={confirmRevoke}
        onClose={() => setRevokeOpen(false)}
      />
    </div>
  );
}

const LIFECYCLE_META: Record<Lifecycle, { title: string; verb: string; destructive: boolean }> = {
  suspend: { title: "Suspend user", verb: "Suspend", destructive: true },
  unsuspend: { title: "Unsuspend user", verb: "Unsuspend", destructive: false },
  disable: { title: "Disable user", verb: "Disable", destructive: true },
  restrict: { title: "Restrict user", verb: "Restrict", destructive: true },
};

function LifecycleModal({
  userId,
  action,
  onClose,
  onSaved,
}: {
  userId: string;
  action: Lifecycle;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const meta = LIFECYCLE_META[action];

  async function submit() {
    setBusy(true);
    setErr(null);
    const r = reason.trim() || undefined;
    try {
      if (action === "suspend") await api.suspendUser(userId, r);
      else if (action === "unsuspend") await api.unsuspendUser(userId, r);
      else if (action === "disable") await api.disableUser(userId, r);
      else await api.restrictUser(userId, r);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={meta.title}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant={meta.destructive ? "danger" : "primary"} loading={busy} onClick={submit}>
            {meta.verb}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Reason" hint="Recorded in the audit log.">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function GrantCreditsModal({
  userId,
  onClose,
  onSaved,
}: {
  userId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.grantUserCredits(userId, {
        amount: Number(amount),
        reason: reason.trim() || undefined,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to grant credits.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Grant credits"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Grant
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Amount" hint="Number of credits to add to the user's organization.">
          <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="1000" />
        </Field>
        <Field label="Reason" hint="Optional. Recorded in the ledger.">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function QuotaResetModal({
  userId,
  onClose,
  onSaved,
}: {
  userId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [metric, setMetric] = useState(QUOTA_METRICS[0]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.quotaReset(userId, { metric, reason: reason.trim() || undefined });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to reset quota.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Reset quota"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Reset
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm text-sand-500">
          Resets the counted usage for the current period without deleting any usage records.
        </p>
        <Field label="Metric">
          <Select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {QUOTA_METRICS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Reason" hint="Recorded in the quota-reset event.">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
