"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { SecurityEvent } from "@/lib/types";
import {
  Badge,
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
} from "@/components/ui";
import { fmtDateShort, fmtNumber, titleCase } from "@/lib/format";

const STATUSES = ["open", "resolved", "ignored"];
const TYPES = [
  "login_success",
  "login_failed",
  "account_locked",
  "password_changed",
  "api_key_created",
  "api_key_revoked",
  "suspicious_login",
  "permission_denied",
];
const PAGE = 50;

const SEVERITY_TONE: Record<string, "bright" | "sand" | "olive" | "inverted"> = {
  info: "olive",
  low: "olive",
  medium: "sand",
  high: "inverted",
  critical: "inverted",
};

function SeverityBadge({ severity }: { severity: string }) {
  return <Badge tone={SEVERITY_TONE[severity] ?? "sand"}>{severity}</Badge>;
}

export default function SecurityPage() {
  const [status, setStatus] = useState("open");
  const [type, setType] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, error, loading, reload } = useApi(
    () =>
      api.listSecurityEvents({
        status: status || undefined,
        type: type || undefined,
        limit: PAGE,
        offset,
      }),
    [status, type, offset],
  );

  const [viewing, setViewing] = useState<SecurityEvent | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function resolve(ev: SecurityEvent, next: string) {
    setBusyId(ev.id);
    try {
      await api.resolveSecurityEvent(ev.id, next);
      reload();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Security"
        description="Authentication and account security events. Triage the open queue."
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
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Type">
          <Select
            value={type}
            onChange={(e) => {
              setType(e.target.value);
              setOffset(0);
            }}
            className="w-52"
          >
            <option value="">All types</option>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {titleCase(t.replace(/_/g, " "))}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No security events" hint="The queue is clear." />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Type</Th>
                <Th>Severity</Th>
                <Th>User</Th>
                <Th>Status</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((ev) => (
                <tr key={ev.id}>
                  <Td className="text-xs text-sand-200">{fmtDateShort(ev.ts)}</Td>
                  <Td className="text-sand-50">{titleCase(ev.type.replace(/_/g, " "))}</Td>
                  <Td>
                    <SeverityBadge severity={ev.severity} />
                  </Td>
                  <Td className="font-mono text-xs text-sand-500">{ev.user_id || "—"}</Td>
                  <Td>
                    <StatusBadge status={ev.status} />
                  </Td>
                  <Td>
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" onClick={() => setViewing(ev)}>
                        Details
                      </Button>
                      {ev.status === "open" && (
                        <>
                          <Button
                            size="sm"
                            loading={busyId === ev.id}
                            onClick={() => resolve(ev, "resolved")}
                          >
                            Resolve
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => resolve(ev, "ignored")}>
                            Ignore
                          </Button>
                        </>
                      )}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="mt-4 flex items-center justify-between text-sm text-sand-200">
            <span>{fmtNumber(data.total)} events</span>
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

      {viewing && <EventModal event={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

function EventModal({ event, onClose }: { event: SecurityEvent; onClose: () => void }) {
  return (
    <Modal
      open
      onClose={onClose}
      title={titleCase(event.type.replace(/_/g, " "))}
      footer={
        <Button variant="primary" onClick={onClose}>
          Close
        </Button>
      }
    >
      <div className="space-y-3 text-sm">
        <Row label="Severity" value={<SeverityBadge severity={event.severity} />} />
        <Row label="Status" value={<StatusBadge status={event.status} />} />
        <Row label="User" value={event.user_id || "—"} mono />
        <Row label="Organization" value={event.organization_id || "—"} mono />
        <Row label="IP hash" value={event.ip_hash || "—"} mono />
        <Row label="User agent" value={event.user_agent || "—"} />
        <Row label="When" value={fmtDateShort(event.ts)} />
        {event.resolved_by && <Row label="Resolved by" value={event.resolved_by} mono />}
        {event.meta && Object.keys(event.meta).length > 0 && (
          <div>
            <div className="label mb-1">Metadata</div>
            <pre className="overflow-x-auto rounded-lg border border-sand-500/30 bg-sand-900/40 p-3 text-xs text-sand-200">
              {JSON.stringify(event.meta, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </Modal>
  );
}

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-sand-500">{label}</span>
      <span className={mono ? "font-mono text-xs text-sand-200" : "text-sand-200"}>{value}</span>
    </div>
  );
}
