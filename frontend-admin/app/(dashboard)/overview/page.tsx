"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import {
  Badge,
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
import { fmtMoney, fmtMs, fmtNumber, fmtPercent, fmtRelative, fmtTokens } from "@/lib/format";

const RANGES = [
  { days: 1, label: "24h" },
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
];

export default function OverviewPage() {
  const { user } = useAuth();
  const [days, setDays] = useState(7);
  const bucket = days <= 2 ? "hour" : "day";

  // Platform overview (§35-37) — refreshed independently of the traffic range selector.
  const { data: platform, error: platformError } = useApi(
    () =>
      Promise.all([api.adminOverview(), api.growth(30), api.planDistribution()]),
    [],
  );
  const [adminOverview, growth, planDist] = platform ?? [];

  // Traffic analytics — keyed to the range selector.
  const { data, error, loading } = useApi(
    () =>
      Promise.all([
        api.overview({ days }),
        api.timeseries({ days, bucket }),
        api.breakdown({ field: "model", days }),
        api.listRequests({ limit: 8 }),
      ]),
    [days],
  );

  const [overview, series, breakdown, recent] = data ?? [];
  const successRate =
    overview && overview.total_requests
      ? overview.successful_requests / overview.total_requests
      : null;

  return (
    <div>
      <PageHeader
        title={`Welcome back, ${user?.name?.split(" ")[0] || "there"}`}
        description="Platform health, revenue, and traffic across every account."
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

      <ErrorBox message={platformError || error} />

      <div className="space-y-6">
        {/* ---- Platform (§35-37) ---------------------------------------- */}
        {adminOverview && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard
                label="Users"
                value={fmtNumber(adminOverview.users.total)}
                sub={`${fmtNumber(adminOverview.users.active)} active`}
              />
              <StatCard
                label="Organizations"
                value={fmtNumber(adminOverview.organizations.total)}
              />
              <StatCard
                label="Active subscriptions"
                value={fmtNumber(adminOverview.subscriptions.active)}
              />
              <StatCard
                label="Est. MRR"
                value={fmtMoney(adminOverview.revenue.estimated_mrr_usd)}
                sub={`${fmtNumber(adminOverview.revenue.credit_liability)} credit liability`}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <Card title="New users (30d)" className="lg:col-span-2">
                {growth && growth.series.length > 0 ? (
                  <>
                    <div className="mb-2 text-xs text-sand-500">
                      {fmtNumber(growth.total_new)} new in the last {growth.days} days
                    </div>
                    <LineChart
                      labels={growth.series.map((p) => p.date)}
                      series={[
                        {
                          name: "New users",
                          tone: "bright",
                          data: growth.series.map((p) => p.new_users),
                        },
                      ]}
                    />
                  </>
                ) : (
                  <p className="py-6 text-center text-sm text-sand-500">No signups yet.</p>
                )}
              </Card>

              <Card title="Plans">
                {planDist && planDist.length > 0 ? (
                  <HBars
                    items={planDist.map((p) => ({
                      label: p.plan_name || p.plan_slug,
                      value: p.subscriptions,
                    }))}
                  />
                ) : (
                  <p className="py-6 text-center text-sm text-sand-500">No subscriptions yet.</p>
                )}
              </Card>
            </div>

            {/* Review queues (§38) */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Link href="/security" className="block">
                <div className="card flex items-center justify-between p-4 transition-colors hover:border-sand-50/40">
                  <div>
                    <div className="text-xs font-medium uppercase tracking-wide text-sand-200">
                      Open security events
                    </div>
                    <div className="mt-2 text-2xl font-semibold text-sand-50">
                      {fmtNumber(adminOverview.queues.open_security_events)}
                    </div>
                  </div>
                  {adminOverview.queues.open_security_events > 0 && (
                    <Badge tone="inverted">review</Badge>
                  )}
                </div>
              </Link>
              <Link href="/risk" className="block">
                <div className="card flex items-center justify-between p-4 transition-colors hover:border-sand-50/40">
                  <div>
                    <div className="text-xs font-medium uppercase tracking-wide text-sand-200">
                      Open risk events
                    </div>
                    <div className="mt-2 text-2xl font-semibold text-sand-50">
                      {fmtNumber(adminOverview.queues.open_risk_events)}
                    </div>
                  </div>
                  {adminOverview.queues.open_risk_events > 0 && (
                    <Badge tone="inverted">review</Badge>
                  )}
                </div>
              </Link>
              <StatCard
                label="Usage (30d)"
                value={fmtNumber(adminOverview.usage_30d.requests)}
                sub={`${fmtTokens(adminOverview.usage_30d.total_tokens)} tokens`}
              />
              <StatCard
                label="Cost (30d)"
                value={fmtMoney(adminOverview.usage_30d.cost_usd)}
                sub={`${fmtNumber(adminOverview.usage_30d.credits_used)} credits used`}
              />
            </div>
          </div>
        )}

        {/* ---- Traffic analytics ---------------------------------------- */}
        {loading || !data ? (
          <Loading />
        ) : (
          <div className="space-y-6">
            <div className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-sand-500">
              Traffic
            </div>
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

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard label="Active users" value={fmtNumber(overview!.active_users)} />
              <StatCard label="Active keys" value={fmtNumber(overview!.active_api_keys)} />
              <StatCard label="Total users" value={fmtNumber(overview!.total_users)} />
              <StatCard label="Total keys" value={fmtNumber(overview!.total_api_keys)} />
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
    </div>
  );
}
