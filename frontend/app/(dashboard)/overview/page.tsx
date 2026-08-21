"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import {
  Card,
  ErrorBox,
  Loading,
  PageHeader,
  StatCard,
  StatusBadge,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { HBars, LineChart } from "@/components/charts";
import {
  fmtMoney,
  fmtMs,
  fmtNumber,
  fmtPercent,
  fmtRelative,
  fmtTokens,
  titleCase,
} from "@/lib/format";

const RANGES = [
  { days: 1, label: "24h" },
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
];

export default function OverviewPage() {
  const { user } = useAuth();
  const [days, setDays] = useState(7);
  const bucket = days <= 2 ? "hour" : "day";

  const { data, error, loading } = useApi(
    () =>
      Promise.all([
        api.accountOverview(),
        api.overview({ days }),
        api.timeseries({ days, bucket }),
        api.breakdown({ field: "model", days }),
        api.listRequests({ limit: 8 }),
      ]),
    [days],
  );

  const [acct, overview, series, breakdown, recent] = data ?? [];
  const successRate =
    overview && overview.total_requests
      ? overview.successful_requests / overview.total_requests
      : null;

  const q = acct?.quota;
  const quotaValue =
    !q || q.unlimited || !q.limit ? "Unlimited" : fmtPercent(q.used / q.limit);
  const quotaSub =
    !q || q.unlimited || q.limit == null
      ? "no monthly cap"
      : `${fmtTokens(q.used)} of ${fmtTokens(q.limit)} used`;

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${user?.name?.split(" ")[0] || "there"}`}
        description="A snapshot of your usage, plan and recent activity."
        actions={
          <div className="flex rounded-lg border border-sand-500/50 p-0.5">
            {RANGES.map((r) => (
              <button
                key={r.days}
                onClick={() => setDays(r.days)}
                className={cx(
                  "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                  days === r.days
                    ? "bg-sand-50 text-sand-900"
                    : "text-sand-200 hover:text-sand-50",
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
          {/* Account summary — plan, credits, quota, recent spend (range-independent). */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Plan"
              value={titleCase(acct!.plan_slug || user?.plan || "free")}
              sub={acct!.organization_id ? "personal org" : undefined}
            />
            <StatCard
              label="Credits"
              value={fmtNumber(acct!.credit_balance)}
              sub="available balance"
            />
            <StatCard label="Monthly quota" value={quotaValue} sub={quotaSub} />
            <StatCard
              label="30-day spend"
              value={fmtMoney(acct!.usage_30d.cost_usd)}
              sub={`${fmtTokens(acct!.usage_30d.total_tokens)} tokens`}
            />
          </div>

          {/* Traffic for the selected range. */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Requests"
              value={fmtNumber(overview!.total_requests)}
              sub={`${fmtNumber(overview!.successful_requests)} successful`}
            />
            <StatCard
              label="Success rate"
              value={successRate === null ? "—" : fmtPercent(successRate)}
              sub={`${fmtNumber(overview!.failed_requests)} failed · ${fmtNumber(
                overview!.rate_limited_requests,
              )} limited`}
            />
            <StatCard
              label="Tokens"
              value={fmtTokens(overview!.total_tokens)}
              sub={`${fmtTokens(overview!.prompt_tokens)} in · ${fmtTokens(
                overview!.completion_tokens,
              )} out`}
            />
            <StatCard
              label="Avg latency"
              value={fmtMs(overview!.avg_latency_ms)}
              sub={`p95 ${fmtMs(overview!.p95_latency_ms)}`}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Traffic" className="lg:col-span-2">
              <LineChart
                labels={series!.points.map((p) => p.ts)}
                series={[
                  {
                    name: "Requests",
                    tone: "bright",
                    data: series!.points.map((p) => p.requests),
                  },
                  {
                    name: "Errors",
                    tone: "olive",
                    data: series!.points.map((p) => p.errors),
                  },
                ]}
              />
            </Card>

            <Card title="Top models">
              <HBars
                items={breakdown!.groups.slice(0, 6).map((g) => ({
                  label: g.key,
                  value: g.requests,
                  hint: fmtTokens(g.tokens),
                }))}
              />
            </Card>
          </div>

          <Card
            title="Recent requests"
            actions={
              <Link href="/requests" className="text-xs text-sand-200 hover:text-sand-50">
                View all →
              </Link>
            }
          >
            {recent!.items.length === 0 ? (
              <p className="py-6 text-center text-sm text-sand-500">No requests yet.</p>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Time</Th>
                    <Th>Model</Th>
                    <Th>Endpoint</Th>
                    <Th>Status</Th>
                    <Th className="text-right">Tokens</Th>
                    <Th className="text-right">Latency</Th>
                  </tr>
                </thead>
                <tbody>
                  {recent!.items.map((r) => (
                    <tr key={r.id}>
                      <Td>
                        <Link href={`/requests/${r.id}`} className="hover:text-sand-50">
                          {fmtRelative(r.started_at)}
                        </Link>
                      </Td>
                      <Td>{r.model || "—"}</Td>
                      <Td className="text-sand-200">{r.endpoint}</Td>
                      <Td>
                        <StatusBadge status={r.status} />
                      </Td>
                      <Td className="text-right">{fmtNumber(r.total_tokens)}</Td>
                      <Td className="text-right">{fmtMs(r.latency_ms)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
