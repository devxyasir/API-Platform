"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Model } from "@/lib/types";
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
import { fmtMoney, fmtNumber, fmtTokens } from "@/lib/format";

const RANGES = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
];

// Rough blended $/1M for a model (average of input & output pricing).
function blended(m: Model | undefined): number {
  if (!m) return 0;
  return (m.input_price_per_1m + m.output_price_per_1m) / 2;
}

export default function UsagePage() {
  const [days, setDays] = useState(30);
  const { data, error, loading } = useApi(
    () =>
      Promise.all([
        api.overview({ days }),
        api.breakdown({ field: "model", days }),
        api.listModels().catch(() => [] as Model[]),
      ]),
    [days],
  );

  const [overview, breakdown, models] = data ?? [];

  const priceOf = (key: string): Model | undefined =>
    models?.find((m) => m.public_id === key || m.aliases.includes(key));

  const rows =
    breakdown?.groups.map((g) => {
      const m = priceOf(g.key);
      const cost = (g.tokens / 1_000_000) * blended(m);
      return { key: g.key, requests: g.requests, tokens: g.tokens, cost };
    }) ?? [];

  const estTotal = rows.reduce((s, r) => s + r.cost, 0);

  return (
    <div>
      <PageHeader
        title="Usage"
        description="Your token consumption and an estimated cost based on model pricing."
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
            <StatCard label="Requests" value={fmtNumber(overview!.total_requests)} />
            <StatCard
              label="Total tokens"
              value={fmtTokens(overview!.total_tokens)}
              sub={`${fmtTokens(overview!.prompt_tokens)} in · ${fmtTokens(
                overview!.completion_tokens,
              )} out`}
            />
            <StatCard label="Estimated cost" value={fmtMoney(estTotal)} sub="blended estimate" />
            <StatCard
              label="Avg tokens / req"
              value={
                overview!.total_requests
                  ? fmtNumber(Math.round(overview!.total_tokens / overview!.total_requests))
                  : "—"
              }
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Tokens by model">
              <HBars
                items={rows.slice(0, 8).map((r) => ({
                  label: r.key,
                  value: r.tokens,
                  hint: fmtTokens(r.tokens),
                }))}
                formatValue={fmtTokens}
              />
            </Card>
            <Card title="Cost by model">
              <Table>
                <thead>
                  <tr>
                    <Th>Model</Th>
                    <Th className="text-right">Tokens</Th>
                    <Th className="text-right">Est. cost</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr>
                      <Td className="text-sand-500">No usage.</Td>
                      <Td />
                      <Td />
                    </tr>
                  ) : (
                    rows.map((r) => (
                      <tr key={r.key}>
                        <Td className="max-w-[14rem] truncate">{r.key}</Td>
                        <Td className="text-right">{fmtTokens(r.tokens)}</Td>
                        <Td className="text-right">{fmtMoney(r.cost)}</Td>
                      </tr>
                    ))
                  )}
                </tbody>
              </Table>
            </Card>
          </div>

          <p className="text-xs text-sand-500">
            Cost is an estimate: it applies each model&apos;s blended (input+output)/2 price to the
            total tokens for that model. For exact figures, use provider billing.
          </p>
        </div>
      )}
    </div>
  );
}
