"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { User, UserStats } from "@/lib/types";
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
  StatCard,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { HBars } from "@/components/charts";
import { fmtDate, fmtNumber, fmtRelative, fmtTokens } from "@/lib/format";

const ROLES = ["admin", "owner", "developer", "viewer"];
const PLANS = ["free", "starter", "pro", "enterprise"];
const STATUSES = ["active", "suspended", "deleted"];
const PAGE = 50;

export default function UsersPage() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useApi(
    () => api.listUsers({ limit: PAGE, offset }),
    [offset],
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [statsFor, setStatsFor] = useState<User | null>(null);

  return (
    <div>
      <PageHeader
        title="Users"
        description="Manage dashboard accounts, roles and plans."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New user
          </Button>
        }
      />

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No users" />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>User</Th>
                <Th>Role</Th>
                <Th>Plan</Th>
                <Th>Status</Th>
                <Th className="text-right">Credits</Th>
                <Th>Created</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((u) => (
                <tr key={u.id}>
                  <Td>
                    <div className="font-medium text-sand-50">{u.name || "—"}</div>
                    <div className="text-xs text-sand-500">{u.email}</div>
                  </Td>
                  <Td>
                    <Badge tone={u.role === "admin" ? "bright" : "olive"}>{u.role}</Badge>
                  </Td>
                  <Td className="capitalize text-sand-200">{u.plan}</Td>
                  <Td>
                    <StatusBadge status={u.status} />
                  </Td>
                  <Td className="text-right">{fmtNumber(u.credits)}</Td>
                  <Td className="text-sand-200">{fmtDate(u.created_at)}</Td>
                  <Td>
                    <div className="flex justify-end gap-1.5">
                      <Link href={`/users/${u.id}`} className="btn-ghost !px-2.5 !py-1.5 !text-xs">
                        View
                      </Link>
                      <Button size="sm" onClick={() => setStatsFor(u)}>
                        Stats
                      </Button>
                      <Button size="sm" onClick={() => setEditing(u)}>
                        Edit
                      </Button>
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="mt-4 flex items-center justify-between text-sm text-sand-200">
            <span>{fmtNumber(data.total)} users</span>
            <div className="flex gap-2">
              <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Previous
              </Button>
              <Button
                size="sm"
                disabled={offset + PAGE >= data.total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      {createOpen && (
        <CreateUserModal
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            reload();
          }}
        />
      )}
      {editing && (
        <EditUserModal
          user={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
      {statsFor && <StatsModal user={statsFor} onClose={() => setStatsFor(null)} />}
    </div>
  );
}

function CreateUserModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("developer");
  const [plan, setPlan] = useState("free");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.createUser({ email, password, name, role, plan });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to create user.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="New user"
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
        <Field label="Email">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" hint="At least 8 characters.">
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Role">
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Plan">
            <Select value={plan} onChange={(e) => setPlan(e.target.value)}>
              {PLANS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function EditUserModal({
  user,
  onClose,
  onSaved,
}: {
  user: User;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(user.name);
  const [role, setRole] = useState(user.role);
  const [plan, setPlan] = useState(user.plan);
  const [status, setStatus] = useState(user.status);
  const [quota, setQuota] = useState(user.quota_tokens != null ? String(user.quota_tokens) : "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.updateUser(user.id, {
        name,
        role,
        plan,
        status,
        quota_tokens: quota.trim() ? Number(quota) : null,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to update user.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Edit ${user.email}`}
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
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Role">
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Plan">
            <Select value={plan} onChange={(e) => setPlan(e.target.value)}>
              {PLANS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Token quota">
            <Input
              type="number"
              value={quota}
              onChange={(e) => setQuota(e.target.value)}
              placeholder="unlimited"
            />
          </Field>
        </div>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function StatsModal({ user, onClose }: { user: User; onClose: () => void }) {
  const { data, error, loading } = useApi<UserStats>(() => api.userStats(user.id, 30), [user.id]);
  return (
    <Modal open onClose={onClose} title={`Usage · ${user.email}`} footer={<Button variant="primary" onClick={onClose}>Close</Button>}>
      <ErrorBox message={error} />
      {loading || !data ? (
        <Loading />
      ) : (
        <div className="space-y-4">
          <p className="text-xs text-sand-500">
            Last 30 days · last active {fmtRelative(data.last_active)}
          </p>
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Requests" value={fmtNumber(data.total_requests)} />
            <StatCard label="Tokens" value={fmtTokens(data.total_tokens)} />
            <StatCard label="Error rate" value={`${(data.error_rate * 100).toFixed(1)}%`} />
          </div>
          <div>
            <div className="label">Top models</div>
            <HBars
              items={(data.top_models || []).map((g) => ({ label: g.key, value: g.requests }))}
            />
          </div>
        </div>
      )}
    </Modal>
  );
}
