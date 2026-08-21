"use client";

// Shared credit-ledger UI used by both the org detail page and the standalone Credits page.

import { useState } from "react";
import { api } from "@/lib/api";
import type { CreditTransaction } from "@/lib/types";
import { Badge, Button, ErrorBox, Field, Input, Modal, Table, Td, Th } from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";

export function LedgerTable({ items }: { items: CreditTransaction[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Time</Th>
          <Th>Type</Th>
          <Th className="text-right">Amount</Th>
          <Th className="text-right">Balance after</Th>
          <Th>Reason</Th>
        </tr>
      </thead>
      <tbody>
        {items.map((t) => (
          <tr key={t.id}>
            <Td className="text-sand-200">{fmtDate(t.ts)}</Td>
            <Td>
              <Badge tone={t.amount >= 0 ? "bright" : "olive"}>{t.type}</Badge>
            </Td>
            <Td className="text-right font-mono">
              {t.amount >= 0 ? "+" : ""}
              {fmtNumber(t.amount)}
            </Td>
            <Td className="text-right font-mono text-sand-200">{fmtNumber(t.balance_after)}</Td>
            <Td className="text-sand-500">{t.reason}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export type CreditAction = "grant" | "refund" | "adjust";

export function CreditActionModal({
  orgId,
  action,
  onClose,
  onSaved,
}: {
  orgId: string;
  action: CreditAction;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const titles: Record<CreditAction, string> = {
    grant: "Grant credits",
    refund: "Refund credits",
    adjust: "Adjust balance",
  };
  const hint =
    action === "adjust"
      ? "Signed delta — positive adds, negative removes. Writes an adjustment ledger entry."
      : "Positive number of credits.";

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const n = Number(amount);
      if (action === "grant")
        await api.grantCredits(orgId, { amount: n, reason: reason.trim() || undefined });
      else if (action === "refund")
        await api.refundCredits(orgId, { amount: n, reason: reason.trim() || undefined });
      else await api.adjustCredits(orgId, { delta: n, reason: reason.trim() });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={titles[action]}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            Confirm
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={action === "adjust" ? "Delta" : "Amount"} hint={hint}>
          <Input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={action === "adjust" ? "-100" : "1000"}
          />
        </Field>
        <Field
          label="Reason"
          hint={action === "adjust" ? "Required." : "Optional. Recorded in the ledger."}
        >
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox message={err} />
      </div>
    </Modal>
  );
}
