"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Invoice, Organization } from "@/lib/types";
import {
  Button,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  StatCard,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fmtDate, fmtMoney, fmtNumber } from "@/lib/format";

const INVOICE_STATUSES = ["draft", "open", "paid", "void", "uncollectible"];
const PAGE = 50;

export default function InvoicesPage() {
  const [status, setStatus] = useState("");
  const [orgId, setOrgId] = useState("");
  const [offset, setOffset] = useState(0);

  const { data: orgs } = useApi(
    () => api.listOrganizations({ include_personal: true, limit: 200 }),
    [],
  );
  const { data, error, loading, reload } = useApi(
    () =>
      api.listInvoices({
        status: status || undefined,
        organization_id: orgId || undefined,
        limit: PAGE,
        offset,
      }),
    [status, orgId, offset],
  );

  const [genOpen, setGenOpen] = useState(false);
  const [viewing, setViewing] = useState<Invoice | null>(null);

  const orgName = (id: string) => orgs?.items.find((o) => o.id === id)?.name || id;

  return (
    <div>
      <PageHeader
        title="Invoices"
        description="Billing-sim invoices generated from usage price snapshots plus the plan fee."
        actions={
          <Button variant="primary" onClick={() => setGenOpen(true)}>
            Generate invoice
          </Button>
        }
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
            {INVOICE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Organization">
          <Select
            value={orgId}
            onChange={(e) => {
              setOrgId(e.target.value);
              setOffset(0);
            }}
            className="w-56"
          >
            <option value="">All organizations</option>
            {orgs?.items.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No invoices" />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Invoice</Th>
                <Th>Organization</Th>
                <Th>Period</Th>
                <Th>Status</Th>
                <Th className="text-right">Total</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((inv) => (
                <tr key={inv.id}>
                  <Td className="font-mono text-xs text-sand-200">{inv.number}</Td>
                  <Td className="text-sand-200">{orgName(inv.organization_id)}</Td>
                  <Td className="text-xs text-sand-200">
                    {fmtDate(inv.period_start)} → {fmtDate(inv.period_end)}
                  </Td>
                  <Td>
                    <StatusBadge status={inv.status} />
                  </Td>
                  <Td className="text-right font-medium text-sand-50">{fmtMoney(inv.total_usd)}</Td>
                  <Td>
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" onClick={() => setViewing(inv)}>
                        View
                      </Button>
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="mt-4 flex items-center justify-between text-sm text-sand-200">
            <span>{fmtNumber(data.total)} invoices</span>
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

      {genOpen && (
        <GenerateModal
          orgs={orgs?.items || []}
          onClose={() => setGenOpen(false)}
          onSaved={() => {
            setGenOpen(false);
            reload();
          }}
        />
      )}
      {viewing && (
        <InvoiceModal
          invoice={viewing}
          orgName={orgName(viewing.organization_id)}
          onClose={() => setViewing(null)}
          onChanged={(updated) => {
            setViewing(updated);
            reload();
          }}
        />
      )}
    </div>
  );
}

function GenerateModal({
  orgs,
  onClose,
  onSaved,
}: {
  orgs: Organization[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [organizationId, setOrganizationId] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [planFee, setPlanFee] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.generateInvoice({
        organization_id: organizationId,
        period_start: periodStart,
        period_end: periodEnd,
        plan_fee_usd: planFee.trim() ? Number(planFee) : undefined,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to generate invoice.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Generate invoice"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Generate
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Organization">
          <Select value={organizationId} onChange={(e) => setOrganizationId(e.target.value)}>
            <option value="">Select…</option>
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Period start">
            <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
          </Field>
          <Field label="Period end">
            <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
          </Field>
        </div>
        <Field label="Plan fee (USD)" hint="Optional. Defaults to the subscription's plan fee.">
          <Input type="number" value={planFee} onChange={(e) => setPlanFee(e.target.value)} placeholder="auto" />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}

function InvoiceModal({
  invoice,
  orgName,
  onClose,
  onChanged,
}: {
  invoice: Invoice;
  orgName: string;
  onClose: () => void;
  onChanged: (updated: Invoice) => void;
}) {
  const [busy, setBusy] = useState<"paid" | "void" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const canPay = invoice.status === "open" || invoice.status === "draft";
  const canVoid = invoice.status !== "void" && invoice.status !== "paid";

  async function act(kind: "paid" | "void") {
    setBusy(kind);
    setErr(null);
    try {
      const updated =
        kind === "paid" ? await api.markInvoicePaid(invoice.id) : await api.voidInvoice(invoice.id);
      onChanged(updated);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Invoice ${invoice.number}`}
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          {canVoid && (
            <Button variant="danger" loading={busy === "void"} onClick={() => act("void")}>
              Void
            </Button>
          )}
          {canPay && (
            <Button variant="primary" loading={busy === "paid"} onClick={() => act("paid")}>
              Mark paid
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-sand-50">{orgName}</div>
            <div className="text-xs text-sand-500">
              {fmtDate(invoice.period_start)} → {fmtDate(invoice.period_end)}
            </div>
          </div>
          <StatusBadge status={invoice.status} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <StatCard label="Plan fee" value={fmtMoney(invoice.plan_fee_usd)} />
          <StatCard label="Usage" value={fmtMoney(invoice.usage_usd)} />
          <StatCard label="Credits applied" value={fmtMoney(invoice.credits_applied_usd)} />
          <StatCard label="Total" value={fmtMoney(invoice.total_usd)} />
        </div>

        {invoice.line_items && invoice.line_items.length > 0 && (
          <div>
            <div className="label mb-1">Line items</div>
            <Table>
              <thead>
                <tr>
                  <Th>Description</Th>
                  <Th className="text-right">Amount</Th>
                </tr>
              </thead>
              <tbody>
                {invoice.line_items.map((li, i) => (
                  <tr key={i}>
                    <Td className="text-sand-200">{li.description || li.model || "—"}</Td>
                    <Td className="text-right">{fmtMoney(Number(li.amount_usd || 0))}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        )}

        <div className="text-xs text-sand-500">
          Issued {invoice.issued_at ? fmtDate(invoice.issued_at) : "—"}
          {invoice.paid_at ? ` · Paid ${fmtDate(invoice.paid_at)}` : ""}
        </div>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
