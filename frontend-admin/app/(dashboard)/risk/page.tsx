"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAsyncAction } from "@/lib/hooks";
import type { RiskEvent } from "@/lib/types";
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

const STATUSES = ["open", "reviewed", "dismissed", "actioned"];
const TYPES = [
  "usage_spike",
  "rapid_key_creation",
  "quota_abuse",
  "repeated_failed_logins",
  "credit_burn",
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

export default function RiskPage() {
  const [status, setStatus] = useState("open");
  const [type, setType] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, error, loading, reload } = useApi(
    () =>
      api.listRiskEvents({
        status: status || undefined,
        type: type || undefined,
        limit: PAGE,
        offset,
      }),
    [status, type, offset],
  );

  const sweep = useAsyncAction(async () => {
    await api.runRiskSweeps();
    reload();
  });

  const [viewing, setViewing] = useState<RiskEvent | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function review(ev: RiskEvent, next: string) {
    setBusyId(ev.id);
    try {
      await api.reviewRiskEvent(ev.id, next);
      reload();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Risk"
        description="Automated abuse-detection signals — usage spikes, quota abuse, credit burn."
        actions={
          <Button variant="primary" loading={sweep.pending} onClick={() => sweep.run()}>
            Run sweeps
          </Button>
        }
      />

      <ErrorBox message={sweep.error} />

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
        <EmptyState title="No risk events" hint="Nothing flagged." />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Type</Th>
                <Th>Severity</Th>
                <Th className="text-right">Score</Th>
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
                  <Td className="text-right font-mono text-sand-200">{ev.score}</Td>
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
                            onClick={() => review(ev, "reviewed")}
                          >
                            Reviewed
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => review(ev, "dismissed")}>
                            Dismiss
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

      {viewing && <RiskModal event={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}

function RiskModal({ event, onClose }: { event: RiskEvent; onClose: () => void }) {
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
        <div className="flex items-start justify-between gap-4">
          <span className="text-sand-500">Severity</span>
          <SeverityBadge severity={event.severity} />
        </div>
        <div className="flex items-start justify-between gap-4">
          <span className="text-sand-500">Score</span>
          <span className="font-mono text-sand-200">{event.score}</span>
        </div>
        <div className="flex items-start justify-between gap-4">
          <span className="text-sand-500">Status</span>
          <StatusBadge status={event.status} />
        </div>
        <div className="flex items-start justify-between gap-4">
          <span className="text-sand-500">User</span>
          <span className="font-mono text-xs text-sand-200">{event.user_id || "—"}</span>
        </div>
        <div className="flex items-start justify-between gap-4">
          <span className="text-sand-500">When</span>
          <span className="text-sand-200">{fmtDateShort(event.ts)}</span>
        </div>
        {event.reviewed_by && (
          <div className="flex items-start justify-between gap-4">
            <span className="text-sand-500">Reviewed by</span>
            <span className="font-mono text-xs text-sand-200">{event.reviewed_by}</span>
          </div>
        )}
        {event.detail && Object.keys(event.detail).length > 0 && (
          <div>
            <div className="label mb-1">Detail</div>
            <pre className="overflow-x-auto rounded-lg border border-sand-500/30 bg-sand-900/40 p-3 text-xs text-sand-200">
              {JSON.stringify(event.detail, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </Modal>
  );
}
