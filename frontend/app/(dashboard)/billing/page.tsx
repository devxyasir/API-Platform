"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import type { Invoice, Plan } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  ErrorBox,
  EmptyState,
  Loading,
  Modal,
  PageHeader,
  StatCard,
  StatusBadge,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { fmtDate, fmtDateShort, fmtMoney, fmtNumber, fmtTokens, titleCase } from "@/lib/format";

function signed(n: number): string {
  return `${n > 0 ? "+" : ""}${fmtNumber(n)}`;
}

export default function BillingPage() {
  const { user } = useAuth();
  const [invoice, setInvoice] = useState<Invoice | null>(null);

  const { data, error, loading } = useApi(
    () =>
      Promise.all([
        api.subscription(),
        api.credits(),
        api.plans(),
        api.invoices({ limit: 50 }),
        api.creditLedger({ limit: 50 }),
      ]),
    [],
  );

  const [sub, balance, plans, invoices, ledger] = data ?? [];
  const currentSlug = sub?.plan_slug || user?.plan;

  return (
    <div>
      <PageHeader
        title="Billing"
        description="Your subscription, credits and invoices. Plan changes are handled by an administrator."
      />

      <ErrorBox message={error} />

      {loading || !data ? (
        <Loading />
      ) : (
        <div className="space-y-6">
          {/* Snapshot */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Plan"
              value={titleCase(sub?.plan_name || currentSlug || "free")}
              sub={sub ? <StatusBadge status={sub.status} /> : "no subscription"}
            />
            <StatCard label="Credit balance" value={fmtNumber(balance!.balance)} sub="credits" />
            <StatCard
              label="Current period"
              value={
                sub?.current_period_end ? fmtDateShort(sub.current_period_end) : "—"
              }
              sub={
                sub?.current_period_end
                  ? sub.cancel_at_period_end
                    ? "cancels at period end"
                    : "renews"
                  : undefined
              }
            />
            <StatCard
              label="Trial"
              value={sub && sub.trial_status !== "none" ? titleCase(sub.trial_status) : "—"}
              sub={sub?.trial_end ? `ends ${fmtDateShort(sub.trial_end)}` : undefined}
            />
          </div>

          {/* Subscription detail */}
          <Card title="Subscription">
            {!sub ? (
              <EmptyState
                title="No active subscription"
                hint="Your account is on the default plan. Contact an administrator to change plans."
              />
            ) : (
              <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                <Row label="Plan">{titleCase(sub.plan_name || sub.plan_slug || "—")}</Row>
                <Row label="Status">
                  <StatusBadge status={sub.status} />
                </Row>
                <Row label="Started">{fmtDate(sub.current_period_start)}</Row>
                <Row label="Renews / ends">
                  {sub.current_period_end ? fmtDate(sub.current_period_end) : "—"}
                </Row>
                <Row label="Provider">{titleCase(sub.provider)}</Row>
                <Row label="Auto-renew">
                  <Badge tone={sub.cancel_at_period_end ? "olive" : "bright"}>
                    {sub.cancel_at_period_end ? "off" : "on"}
                  </Badge>
                </Row>
              </div>
            )}
          </Card>

          {/* Plan catalogue */}
          <div>
            <h2 className="mb-3 text-sm font-semibold text-sand-50">Available plans</h2>
            {!plans || plans.length === 0 ? (
              <EmptyState title="No plans published" />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {plans.map((p) => (
                  <PlanCard key={p.id} plan={p} current={p.slug === currentSlug} />
                ))}
              </div>
            )}
          </div>

          {/* Invoices */}
          <Card title="Invoices">
            {!invoices || invoices.items.length === 0 ? (
              <p className="py-6 text-center text-sm text-sand-500">No invoices yet.</p>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Number</Th>
                    <Th>Period</Th>
                    <Th>Status</Th>
                    <Th className="text-right">Total</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {invoices.items.map((inv) => (
                    <tr key={inv.id} className="transition-colors hover:bg-sand-500/10">
                      <Td className="font-medium text-sand-50">{inv.number}</Td>
                      <Td className="text-sand-200">
                        {fmtDateShort(inv.period_start)} – {fmtDateShort(inv.period_end)}
                      </Td>
                      <Td>
                        <StatusBadge status={inv.status} />
                      </Td>
                      <Td className="text-right">{fmtMoney(inv.total_usd)}</Td>
                      <Td className="text-right">
                        <Button size="sm" onClick={() => setInvoice(inv)}>
                          Details
                        </Button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          {/* Credit ledger */}
          <Card title="Credit history">
            {!ledger || ledger.items.length === 0 ? (
              <p className="py-6 text-center text-sm text-sand-500">No credit activity yet.</p>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>Type</Th>
                    <Th>Reason</Th>
                    <Th className="text-right">Amount</Th>
                    <Th className="text-right">Balance</Th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.items.map((t) => (
                    <tr key={t.id}>
                      <Td className="text-sand-200">{fmtDate(t.ts)}</Td>
                      <Td>
                        <Badge tone="sand">{t.type}</Badge>
                      </Td>
                      <Td className="max-w-[18rem] truncate text-sand-200">{t.reason || "—"}</Td>
                      <Td
                        className={cx(
                          "text-right font-medium",
                          t.amount >= 0 ? "text-sand-50" : "text-sand-200",
                        )}
                      >
                        {signed(t.amount)}
                      </Td>
                      <Td className="text-right">{fmtNumber(t.balance_after)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </div>
      )}

      <InvoiceModal invoice={invoice} onClose={() => setInvoice(null)} />
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-sand-500/20 py-2 last:border-0">
      <span className="text-sm text-sand-500">{label}</span>
      <span className="text-right text-sm text-sand-50">{children}</span>
    </div>
  );
}

function PlanCard({ plan, current }: { plan: Plan; current: boolean }) {
  const seats = plan.limits?.["monthly_token_quota"];
  return (
    <div
      className={cx(
        "card flex flex-col p-4",
        current ? "ring-1 ring-sand-50/50" : "",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-sand-50">{plan.name}</h3>
        {current && <Badge tone="bright">current</Badge>}
      </div>
      {plan.description && (
        <p className="mt-1 text-xs text-sand-500">{plan.description}</p>
      )}
      <div className="mt-3 text-2xl font-semibold text-sand-50">
        {plan.price_monthly_usd ? fmtMoney(plan.price_monthly_usd) : "Free"}
        {plan.price_monthly_usd ? (
          <span className="text-sm font-normal text-sand-500">/mo</span>
        ) : null}
      </div>
      <ul className="mt-3 space-y-1 text-xs text-sand-200">
        {plan.monthly_credits > 0 && <li>{fmtNumber(plan.monthly_credits)} credits / month</li>}
        {plan.trial_days > 0 && <li>{plan.trial_days}-day trial</li>}
        {seats != null && <li>{fmtTokens(seats)} tokens / month</li>}
        <li>{plan.models.length > 0 ? `${plan.models.length} models` : "All models"}</li>
      </ul>
    </div>
  );
}

function InvoiceModal({ invoice, onClose }: { invoice: Invoice | null; onClose: () => void }) {
  if (!invoice) return null;
  const items = Array.isArray(invoice.line_items) ? invoice.line_items : [];
  return (
    <Modal open={!!invoice} onClose={onClose} title={`Invoice ${invoice.number}`}>
      <div className="space-y-4">
        <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
          <Row label="Status">
            <StatusBadge status={invoice.status} />
          </Row>
          <Row label="Period">
            {fmtDateShort(invoice.period_start)} – {fmtDateShort(invoice.period_end)}
          </Row>
          <Row label="Issued">{invoice.issued_at ? fmtDate(invoice.issued_at) : "—"}</Row>
          <Row label="Paid">{invoice.paid_at ? fmtDate(invoice.paid_at) : "—"}</Row>
        </div>

        {items.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th>Item</Th>
                <Th className="text-right">Amount</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((li, i) => (
                <tr key={i}>
                  <Td className="text-sand-200">
                    {li.description || li.model || `Line ${i + 1}`}
                  </Td>
                  <Td className="text-right">
                    {typeof li.amount_usd === "number" ? fmtMoney(li.amount_usd) : "—"}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}

        <div className="space-y-1.5 border-t border-sand-500/35 pt-3 text-sm">
          <Row label="Plan fee">{fmtMoney(invoice.plan_fee_usd)}</Row>
          <Row label="Usage">{fmtMoney(invoice.usage_usd)}</Row>
          <Row label="Credits applied">−{fmtMoney(invoice.credits_applied_usd)}</Row>
          <div className="flex items-center justify-between gap-4 pt-1 text-base font-semibold text-sand-50">
            <span>Total</span>
            <span>{fmtMoney(invoice.total_usd)}</span>
          </div>
        </div>
      </div>
    </Modal>
  );
}
