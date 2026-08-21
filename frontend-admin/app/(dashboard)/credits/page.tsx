"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Organization } from "@/lib/types";
import {
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Loading,
  PageHeader,
  Select,
  StatCard,
} from "@/components/ui";
import { CreditActionModal, LedgerTable, type CreditAction } from "@/components/credits";
import { fmtNumber } from "@/lib/format";

export default function CreditsPage() {
  const { data: orgs, error: orgsError, loading: orgsLoading } = useApi(
    () => api.listOrganizations({ include_personal: true, limit: 200 }),
    [],
  );
  const [orgId, setOrgId] = useState("");

  return (
    <div>
      <PageHeader
        title="Credits"
        description="Inspect a credit ledger and grant, refund, or adjust an organization's balance."
      />

      <ErrorBox message={orgsError} />

      {orgsLoading && !orgs ? (
        <Loading />
      ) : !orgs || orgs.items.length === 0 ? (
        <EmptyState title="No organizations" hint="Create an organization first." />
      ) : (
        <>
          <div className="mb-6 max-w-md">
            <Field label="Organization" hint="Select an organization to manage its credits.">
              <Select value={orgId} onChange={(e) => setOrgId(e.target.value)}>
                <option value="">Select an organization…</option>
                {orgs.items.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                    {o.is_personal ? " (personal)" : ""} · {fmtNumber(o.credit_balance)} cr
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          {orgId ? (
            <CreditsPanel orgId={orgId} org={orgs.items.find((o) => o.id === orgId)} />
          ) : (
            <EmptyState title="No organization selected" hint="Pick one above to view its ledger." />
          )}
        </>
      )}
    </div>
  );
}

function CreditsPanel({ orgId, org }: { orgId: string; org?: Organization }) {
  const { data, error, loading, reload } = useApi(
    () => Promise.all([api.creditBalance(orgId), api.creditLedger(orgId, { limit: 100 })]),
    [orgId],
  );
  const [balance, ledger] = data ?? [];
  const [action, setAction] = useState<CreditAction | null>(null);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Balance"
          value={balance ? fmtNumber(balance.balance) : "—"}
          sub="credits"
        />
        {org && <StatCard label="Organization" value={org.name} sub={org.slug} />}
      </div>

      <Card
        title="Ledger"
        actions={
          <div className="flex gap-2">
            <Button size="sm" onClick={() => setAction("grant")}>
              Grant
            </Button>
            <Button size="sm" onClick={() => setAction("refund")}>
              Refund
            </Button>
            <Button size="sm" onClick={() => setAction("adjust")}>
              Adjust
            </Button>
          </div>
        }
      >
        <ErrorBox message={error} />
        {loading && !data ? (
          <Loading />
        ) : !ledger || ledger.items.length === 0 ? (
          <EmptyState
            title="No credit transactions"
            hint="Grants, usage, refunds and adjustments appear here."
          />
        ) : (
          <LedgerTable items={ledger.items} />
        )}
      </Card>

      {action && (
        <CreditActionModal
          orgId={orgId}
          action={action}
          onClose={() => setAction(null)}
          onSaved={() => {
            setAction(null);
            reload();
          }}
        />
      )}
    </div>
  );
}
