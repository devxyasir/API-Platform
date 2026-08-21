"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  Badge,
  Card,
  ErrorBox,
  Loading,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { fmtDate, fmtMs, fmtNumber } from "@/lib/format";
import type { ReactNode } from "react";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-sand-500/20 py-2 last:border-0">
      <span className="text-sm text-sand-500">{label}</span>
      <span className="text-right text-sm text-sand-50">{children}</span>
    </div>
  );
}

function Content({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="label">{label}</div>
      {value ? (
        <pre className="max-h-80 overflow-auto rounded-lg border border-sand-500/40 bg-sand-900/60 p-3 text-xs text-sand-50">
          {value}
        </pre>
      ) : (
        <p className="rounded-lg border border-dashed border-sand-500/40 p-3 text-xs text-sand-500">
          Not captured. Content logging is disabled by default (LOG_REQUEST_CONTENT).
        </p>
      )}
    </div>
  );
}

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { data: r, error, loading } = useApi(() => api.getRequest(id), [id]);

  return (
    <div>
      <PageHeader
        title="Request detail"
        description={id}
        actions={
          <Link href="/requests" className="btn-ghost !px-3 !py-1.5 !text-xs">
            ← Back
          </Link>
        }
      />

      <ErrorBox message={error} />

      {loading || !r ? (
        <Loading />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Summary">
            <Row label="Status">
              <StatusBadge status={r.status} />
            </Row>
            <Row label="HTTP code">{r.status_code}</Row>
            <Row label="Model">{r.model || "—"}</Row>
            <Row label="Upstream model">{r.upstream_model || "—"}</Row>
            <Row label="Provider">{r.provider}</Row>
            <Row label="Endpoint">{r.endpoint}</Row>
            <Row label="Method">{r.method}</Row>
            <Row label="Format">{r.api_format}</Row>
            <Row label="Streamed">
              <Badge tone={r.stream ? "bright" : "olive"}>{r.stream ? "yes" : "no"}</Badge>
            </Row>
          </Card>

          <Card title="Timing & tokens">
            <Row label="Started">{fmtDate(r.started_at)}</Row>
            <Row label="Completed">{fmtDate(r.completed_at)}</Row>
            <Row label="Latency">{fmtMs(r.latency_ms)}</Row>
            <Row label="Time to first token">{r.ttft_ms != null ? fmtMs(r.ttft_ms) : "—"}</Row>
            <Row label="Prompt tokens">{fmtNumber(r.prompt_tokens)}</Row>
            <Row label="Completion tokens">{fmtNumber(r.completion_tokens)}</Row>
            <Row label="Total tokens">{fmtNumber(r.total_tokens)}</Row>
            <Row label="Token source">{r.token_count_source}</Row>
            <Row label="Provider request id">{r.provider_request_id || "—"}</Row>
          </Card>

          {(r.error_type || r.error_code || r.error_message) && (
            <Card title="Error" className="lg:col-span-2">
              <Row label="Type">{r.error_type || "—"}</Row>
              <Row label="Code">{r.error_code || "—"}</Row>
              <Row label="Message">{r.error_message || "—"}</Row>
            </Card>
          )}

          <Card title="Client" className="lg:col-span-2">
            <Row label="IP (hashed)">{r.ip_hash || "—"}</Row>
            <Row label="User agent">{r.user_agent || "—"}</Row>
            <Row label="User id">{r.user_id || "—"}</Row>
            <Row label="API key id">{r.api_key_id || "—"}</Row>
            <Row label="Project id">{r.project_id || "—"}</Row>
          </Card>

          <div className="space-y-4 lg:col-span-2">
            <Content label="Request content" value={r.request_content} />
            <Content label="Response content" value={r.response_content} />
          </div>
        </div>
      )}
    </div>
  );
}
