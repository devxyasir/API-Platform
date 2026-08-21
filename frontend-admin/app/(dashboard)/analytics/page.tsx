"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  Card,
  ErrorBox,
  Loading,
  PageHeader,
  Select,
  StatCard,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { HBars, LineChart } from "@/components/charts";
import { fmtMs, fmtNumber, fmtPercent, fmtTokens, titleCase } from "@/lib/format";

const RANGES = [
  { days: 1, label: "24h" },
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
];

const FIELDS = ["model", "endpoint", "status", "provider", "api_format"];

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [field, setField] = useState("model");
  const bucket = days <= 2 ? "hour" : "day";

  const { data, error, loading } = useApi(
    () =>
      Promise.all([
        api.overview({ days }),
        api.timeseries({ days, bucket }),
        api.breakdown({ field, days }),
      ]),
    [days, field],
  );

  const [overview, series, breakdown] = data ?? [];

  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Traffic, latency and token usage over time."
        actions={
          <div className="flex rounded-lg border border-sand-500/50 p-0.5">
            {RANGES.map((r) => (
              <button
                key={r.days}
                onClick={() => setDays(r.days)}
                className={cx(
                  "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                  days === r.days ? "bg-sand-50 text-sand-900" : "text-sand-200 hover:text-sand-50",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        }
      />

      <ErrorBox message={error} />

      {loading || !data ? (
        <Loading />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="p50 latency" value={fmtMs(overview!.p50_latency_ms)} />
            <StatCard label="p95 latency" value={fmtMs(overview!.p95_latency_ms)} />
            <StatCard label="p99 latency" value={fmtMs(overview!.p99_latency_ms)} />
            <StatCard
              label="Error rate"
              value={fmtPercent(overview!.error_rate)}
              sub={`${fmtNumber(overview!.provider_errors)} upstream errors`}
            />
          </div>

          <Card title="Requests & errors">
            <LineChart
              labels={series!.points.map((p) => p.ts)}
              series={[
                { name: "Requests", tone: "bright", data: series!.points.map((p) => p.requests) },
                { name: "Errors", tone: "olive", data: series!.points.map((p) => p.errors) },
              ]}
            />
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Tokens">
              <LineChart
                labels={series!.points.map((p) => p.ts)}
                yFormat={fmtTokens}
                series={[
                  { name: "Tokens", tone: "sand", data: series!.points.map((p) => p.tokens) },
                ]}
              />
            </Card>
            <Card title="Avg latency">
              <LineChart
                labels={series!.points.map((p) => p.ts)}
                yFormat={(n) => `${Math.round(n)}ms`}
                series={[
                  {
                    name: "Latency",
                    tone: "bright",
                    data: series!.points.map((p) => p.avg_latency_ms),
                  },
                ]}
              />
            </Card>
          </div>

          <Card
            title="Breakdown"
            actions={
              <Select
                value={field}
                onChange={(e) => setField(e.target.value)}
                className="!w-auto !py-1 !text-xs"
              >
                {FIELDS.map((f) => (
                  <option key={f} value={f}>
                    By {titleCase(f)}
                  </option>
                ))}
              </Select>
            }
          >
            <div className="grid gap-6 lg:grid-cols-2">
              <HBars
                items={breakdown!.groups.slice(0, 10).map((g) => ({
                  label: g.key,
                  value: g.requests,
                }))}
              />
              <Table>
                <thead>
                  <tr>
                    <Th>{titleCase(field)}</Th>
                    <Th className="text-right">Requests</Th>
                    <Th className="text-right">Tokens</Th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown!.groups.slice(0, 10).map((g) => (
                    <tr key={g.key}>
                      <Td className="max-w-[16rem] truncate">{g.key}</Td>
                      <Td className="text-right">{fmtNumber(g.requests)}</Td>
                      <Td className="text-right">{fmtTokens(g.tokens)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
