"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Organization } from "@/lib/types";
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
  StatusBadge,
  Table,
  Td,
  Th,
  Toggle,
} from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";

const ORG_STATUSES = ["active", "suspended", "restricted", "deleted"];
const PAGE = 50;

export default function OrganizationsPage() {
  const [status, setStatus] = useState("");
  const [includePersonal, setIncludePersonal] = useState(true);
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useApi(
    () =>
      api.listOrganizations({
        status: status || undefined,
        include_personal: includePersonal,
        limit: PAGE,
        offset,
      }),
    [status, includePersonal, offset],
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [statusFor, setStatusFor] = useState<Organization | null>(null);

  return (
    <div>
      <PageHeader
        title="Organizations"
        description="Every organization on the platform — the owner of plans, credits, and usage."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New organization
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
            {ORG_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 pb-2 text-sm text-sand-200">
          <Toggle
            checked={includePersonal}
            onChange={(v) => {
              setIncludePersonal(v);
              setOffset(0);
            }}
          />
          Include personal
        </label>
      </div>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No organizations" />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Organization</Th>
                <Th>Owner</Th>
                <Th>Status</Th>
                <Th>Type</Th>
                <Th className="text-right">Credits</Th>
                <Th>Created</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((o) => (
                <tr key={o.id}>
                  <Td>
                    <div className="font-medium text-sand-50">{o.name}</div>
                    <div className="font-mono text-xs text-sand-500">{o.slug}</div>
                  </Td>
                  <Td className="font-mono text-xs text-sand-500">{o.owner_id}</Td>
                  <Td>
                    <StatusBadge status={o.status} />
                  </Td>
                  <Td>
                    <Badge tone={o.is_personal ? "olive" : "sand"}>
                      {o.is_personal ? "personal" : "team"}
                    </Badge>
                  </Td>
                  <Td className="text-right">{fmtNumber(o.credit_balance)}</Td>
                  <Td className="text-sand-200">{fmtDate(o.created_at)}</Td>
                  <Td>
                    <div className="flex justify-end gap-1.5">
                      <Link
                        href={`/organizations/${o.id}`}
                        className="btn-ghost !px-2.5 !py-1.5 !text-xs"
                      >
                        View
                      </Link>
                      <Button size="sm" onClick={() => setStatusFor(o)}>
                        Status
                      </Button>
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="mt-4 flex items-center justify-between text-sm text-sand-200">
            <span>{fmtNumber(data.total)} organizations</span>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
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
        <CreateOrgModal
          onClose={() => setCreateOpen(false)}
          onSaved={() => {
            setCreateOpen(false);
            reload();
          }}
        />
      )}
      {statusFor && (
        <StatusModal
          org={statusFor}
          onClose={() => setStatusFor(null)}
          onSaved={() => {
            setStatusFor(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function CreateOrgModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [slug, setSlug] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.createOrganization({
        name: name.trim(),
        owner_id: ownerId.trim(),
        slug: slug.trim() || null,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to create organization.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="New organization"
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
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Inc" />
        </Field>
        <Field label="Owner user id">
          <Input value={ownerId} onChange={(e) => setOwnerId(e.target.value)} placeholder="usr_…" />
        </Field>
        <Field label="Slug" hint="Optional. Auto-generated from the name if left blank.">
          <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="acme" />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function StatusModal({
  org,
  onClose,
  onSaved,
}: {
  org: Organization;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState(org.status);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.setOrgStatus(org.id, { status, reason: reason.trim() || undefined });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to change status.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Status · ${org.name}`}
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
        <Field label="Status">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {ORG_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Reason" hint="Recorded in the audit log.">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
