"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  Card,
  ErrorBox,
  Loading,
  PageHeader,
  StatCard,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { HBars } from "@/components/charts";
import { fmtMoney, fmtNumber, fmtPercent, fmtTokens } from "@/lib/format";

const RANGES = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
];

export default function UsagePage() {
  const [days, setDays] = useState(30);
  const { data, error, loading } = useApi(
    () =>
      Promise.all([
        api.usageSummary({ days }),
        api.usageByModel({ days }),
        api.quota(),
      ]),
    [days],
  );

  const [summary, byModel, quota] = data ?? [];
  const groups = byModel?.groups ?? [];
  const avgPerReq =
    summary && summary.requests
      ? Math.round(summary.total_tokens / summary.requests)
      : null;

  const quotaPct =
    quota && !quota.unlimited && quota.limit ? Math.min(1, quota.used / quota.limit) : null;

  return (
    <div>
      <PageHeader
        title="Usage"
        description="Your token consumption and cost, straight from the billing records."
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
            <StatCard label="Requests" value={fmtNumber(summary!.requests)} />
            <StatCard label="Total tokens" value={fmtTokens(summary!.total_tokens)} />
            <StatCard
              label="Cost"
              value={fmtMoney(summary!.cost_usd)}
              sub={`over the last ${days}d`}
            />
            <StatCard
              label="Avg tokens / req"
              value={avgPerReq === null ? "—" : fmtNumber(avgPerReq)}
              sub={
                summary!.credits_used ? `${fmtNumber(summary!.credits_used)} credits used` : undefined
              }
            />
          </div>

          <Card title="Monthly token quota">
            {!quota || quota.unlimited || quota.limit == null ? (
              <div className="flex items-center justify-between py-2 text-sm">
                <span className="text-sand-200">Current period usage</span>
                <span className="text-sand-50">
                  {fmtTokens(quota?.used ?? 0)} · <span className="text-sand-500">no cap</span>
                </span>
              </div>
            ) : (
              <div className="space-y-2 py-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-sand-200">
                    {fmtTokens(quota.used)} of {fmtTokens(quota.limit)}
                  </span>
                  <span className="text-sand-50">
                    {fmtTokens(quota.remaining ?? 0)} left · {fmtPercent(quotaPct ?? 0)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-sand-500/25">
                  <div
                    className="h-full rounded-full bg-sand-50 transition-all"
                    style={{ width: `${Math.round((quotaPct ?? 0) * 100)}%` }}
                  />
                </div>
              </div>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Tokens by model">
              {groups.length === 0 ? (
                <p className="py-6 text-center text-sm text-sand-500">No usage in this window.</p>
              ) : (
                <HBars
                  items={groups.slice(0, 8).map((g) => ({
                    label: g.model,
                    value: g.total_tokens,
                    hint: fmtTokens(g.total_tokens),
                  }))}
                  formatValue={fmtTokens}
                />
              )}
            </Card>
            <Card title="Cost by model">
              <Table>
                <thead>
                  <tr>
                    <Th>Model</Th>
                    <Th className="text-right">Requests</Th>
                    <Th className="text-right">Tokens</Th>
                    <Th className="text-right">Cost</Th>
                  </tr>
                </thead>
                <tbody>
                  {groups.length === 0 ? (
                    <tr>
                      <Td className="text-sand-500">No usage.</Td>
                      <Td />
                      <Td />
                      <Td />
                    </tr>
                  ) : (
                    groups.map((g) => (
                      <tr key={g.model}>
                        <Td className="max-w-[14rem] truncate">{g.model}</Td>
                        <Td className="text-right">{fmtNumber(g.requests)}</Td>
                        <Td className="text-right">{fmtTokens(g.total_tokens)}</Td>
                        <Td className="text-right">{fmtMoney(g.cost_usd)}</Td>
                      </tr>
                    ))
                  )}
                </tbody>
              </Table>
            </Card>
          </div>

          <p className="text-xs text-sand-500">
            Cost reflects the price recorded on each request at the time it ran. The monthly
            quota resets at the start of your billing period.
          </p>
        </div>
      )}
    </div>
  );
}
