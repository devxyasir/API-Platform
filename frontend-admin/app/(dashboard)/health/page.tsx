"use client";

import { useEffect } from "react";
import { api, API_BASE } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Card, ErrorBox, Loading, PageHeader, StatusBadge, Button } from "@/components/ui";
import { fmtDate } from "@/lib/format";
import type { ReactNode } from "react";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-sand-500/20 py-3 last:border-0">
      <span className="text-sm text-sand-500">{label}</span>
      <span className="text-right text-sm text-sand-50">{children}</span>
    </div>
  );
}

export default function HealthPage() {
  const { data, error, loading, reload } = useApi(() => api.health(), []);

  // Poll every 10s for a live view.
  useEffect(() => {
    const t = setInterval(reload, 10_000);
    return () => clearInterval(t);
  }, [reload]);

  return (
    <div>
      <PageHeader
        title="Health"
        description="Live status of the gateway and its dependencies."
        actions={
          <Button size="sm" onClick={reload}>
            Refresh
          </Button>
        }
      />

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Status">
            <Row label="Overall">
              <StatusBadge status={data.status} />
            </Row>
            <Row label="Database">
              <StatusBadge status={data.database} />
            </Row>
            <Row label="Cache">
              <span className="capitalize">{data.cache}</span>
            </Row>
            <Row label="Upstream circuit">
              <StatusBadge status={data.upstream_circuit} />
            </Row>
          </Card>

          <Card title="Deployment">
            <Row label="Application">{data.app}</Row>
            <Row label="Environment">
              <span className="capitalize">{data.env}</span>
            </Row>
            <Row label="API base">
              <code className="text-sand-200">{API_BASE}</code>
            </Row>
            <Row label="Checked at">{fmtDate(data.time)}</Row>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
