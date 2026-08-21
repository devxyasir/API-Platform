"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { OrgMember, Organization } from "@/lib/types";
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
  Table,
  Tabs,
  Td,
  Th,
} from "@/components/ui";
import { CreditActionModal, LedgerTable, type CreditAction } from "@/components/credits";
import { fmtDate, fmtNumber } from "@/lib/format";

const ORG_ROLES = ["owner", "admin", "developer", "billing", "viewer"];

export default function OrganizationDetailPage() {
  const params = useParams<{ id: string }>();
  const orgId = params.id;
  const [tab, setTab] = useState("overview");

  const { data: org, error, loading, reload } = useApi<Organization>(
    () => api.getOrganization(orgId),
    [orgId],
  );

  return (
    <div>
      <PageHeader
        title={org?.name || "Organization"}
        description={org ? org.slug : undefined}
        actions={
          <Link href="/organizations" className="btn-ghost !px-3 !py-1.5 !text-xs">
            ← All organizations
          </Link>
        }
      />

      <ErrorBox message={error} />

      {loading && !org ? (
        <Loading />
      ) : !org ? (
        <EmptyState title="Organization not found" />
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Status" value={<StatusBadge status={org.status} />} />
            <StatCard
              label="Type"
              value={
                <Badge tone={org.is_personal ? "olive" : "sand"}>
                  {org.is_personal ? "personal" : "team"}
                </Badge>
              }
            />
            <StatCard label="Credit balance" value={fmtNumber(org.credit_balance)} />
            <StatCard label="Created" value={fmtDate(org.created_at)} />
          </div>

          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "overview", label: "Overview" },
              { key: "members", label: "Members" },
              { key: "credits", label: "Credits" },
              { key: "history", label: "Plan history" },
            ]}
          />

          {tab === "overview" && <OverviewTab org={org} onChanged={reload} />}
          {tab === "members" && <MembersTab orgId={orgId} />}
          {tab === "credits" && <CreditsTab orgId={orgId} onChanged={reload} />}
          {tab === "history" && <HistoryTab orgId={orgId} />}
        </>
      )}
    </div>
  );
}

function OverviewTab({ org, onChanged }: { org: Organization; onChanged: () => void }) {
  const [name, setName] = useState(org.name);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function save() {
    setBusy(true);
    setErr(null);
    setOk(false);
    try {
      await api.updateOrganization(org.id, { name: name.trim() });
      setOk(true);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Details" className="max-w-lg">
      <div className="space-y-4">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="label">Owner</div>
            <div className="font-mono text-xs text-sand-200">{org.owner_id}</div>
          </div>
          <div>
            <div className="label">Organization id</div>
            <div className="font-mono text-xs text-sand-200">{org.id}</div>
          </div>
        </div>
        <ErrorBox message={err} />
        <div className="flex items-center gap-3">
          <Button variant="primary" loading={busy} onClick={save}>
            Save
          </Button>
          {ok && <span className="text-xs text-sand-500">Saved ✓</span>}
        </div>
      </div>
    </Card>
  );
}

function MembersTab({ orgId }: { orgId: string }) {
  const { data, error, loading, reload } = useApi<OrgMember[]>(
    () => api.listOrgMembers(orgId),
    [orgId],
  );
  const [addOpen, setAddOpen] = useState(false);
  const [removing, setRemoving] = useState<OrgMember | null>(null);
  const [busy, setBusy] = useState(false);

  async function changeRole(m: OrgMember, role: string) {
    await api.updateOrgMember(orgId, m.user_id, { role });
    reload();
  }

  async function confirmRemove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.removeOrgMember(orgId, removing.user_id);
      setRemoving(null);
      reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button variant="primary" onClick={() => setAddOpen(true)}>
          Add member
        </Button>
      </div>
      <ErrorBox message={error} />
      {loading && !data ? (
        <Loading />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No members" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>User</Th>
              <Th>Role</Th>
              <Th>Status</Th>
              <Th>Joined</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {data.map((m) => (
              <tr key={m.id}>
                <Td className="font-mono text-xs text-sand-200">{m.user_id}</Td>
                <Td>
                  <Select
                    value={m.role}
                    onChange={(e) => changeRole(m, e.target.value)}
                    className="w-32"
                  >
                    {ORG_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </Select>
                </Td>
                <Td>
                  <StatusBadge status={m.status} />
                </Td>
                <Td className="text-sand-200">{fmtDate(m.joined_at)}</Td>
                <Td>
                  <div className="flex justify-end">
                    <Button size="sm" variant="danger" onClick={() => setRemoving(m)}>
                      Remove
                    </Button>
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {addOpen && (
        <AddMemberModal
          orgId={orgId}
          onClose={() => setAddOpen(false)}
          onSaved={() => {
            setAddOpen(false);
            reload();
          }}
        />
      )}
      <ConfirmModal
        open={!!removing}
        title="Remove member"
        message={`Remove ${removing?.user_id} from this organization?`}
        confirmLabel="Remove"
        destructive
        busy={busy}
        onConfirm={confirmRemove}
        onClose={() => setRemoving(null)}
      />
    </div>
  );
}

function AddMemberModal({
  orgId,
  onClose,
  onSaved,
}: {
  orgId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("developer");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.addOrgMember(orgId, { user_id: userId.trim(), role });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to add member.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Add member"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Add
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="User id">
          <Input value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="usr_…" />
        </Field>
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {ORG_ROLES.map((r) => (
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

function CreditsTab({ orgId, onChanged }: { orgId: string; onChanged: () => void }) {
  const { data, error, loading, reload } = useApi(
    () => Promise.all([api.creditBalance(orgId), api.creditLedger(orgId, { limit: 50 })]),
    [orgId],
  );
  const [balance, ledger] = data ?? [];
  const [action, setAction] = useState<CreditAction | null>(null);

  function refresh() {
    reload();
    onChanged();
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-sand-200">
          Balance:{" "}
          <span className="font-semibold text-sand-50">
            {balance ? fmtNumber(balance.balance) : "—"}
          </span>{" "}
          credits
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setAction("grant")}>
            Grant
          </Button>
          <Button size="sm" onClick={() => setAction("refund")}>
            Refund
          </Button>
          <Button size="sm" onClick={() => setAction("adjust")}>
            Adjust
          </Button>
        </div>
      </div>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !ledger || ledger.items.length === 0 ? (
        <EmptyState
          title="No credit transactions"
          hint="Grants, usage, refunds and adjustments appear here."
        />
      ) : (
        <LedgerTable items={ledger.items} />
      )}

      {action && (
        <CreditActionModal
          orgId={orgId}
          action={action}
          onClose={() => setAction(null)}
          onSaved={() => {
            setAction(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function HistoryTab({ orgId }: { orgId: string }) {
  const { data, error, loading } = useApi(
    () => api.subscriptionHistory(orgId, { limit: 50 }),
    [orgId],
  );

  return (
    <div>
      <ErrorBox message={error} />
      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No plan changes" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Time</Th>
              <Th>From</Th>
              <Th>To</Th>
              <Th>Reason</Th>
              <Th>Changed by</Th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((h) => (
              <tr key={h.id}>
                <Td className="text-sand-200">{fmtDate(h.ts)}</Td>
                <Td className="text-sand-500">{h.old_plan || "—"}</Td>
                <Td className="text-sand-50">{h.new_plan}</Td>
                <Td className="text-sand-500">{h.reason}</Td>
                <Td className="font-mono text-xs text-sand-500">{h.changed_by || "system"}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
