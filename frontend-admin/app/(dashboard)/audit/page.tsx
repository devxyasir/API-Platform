"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  PageHeader,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";

const PAGE = 100;

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [actionInput, setActionInput] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, error, loading } = useApi(
    () => api.listAudit({ action, limit: PAGE, offset }),
    [action, offset],
  );

  return (
    <div>
      <PageHeader title="Audit Log" description="Every administrative action, most recent first." />

      <Card className="mb-4">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setAction(actionInput.trim());
            setOffset(0);
          }}
        >
          <Field label="Action">
            <Input
              value={actionInput}
              onChange={(e) => setActionInput(e.target.value)}
              placeholder="e.g. api_key.created"
              className="!w-60"
            />
          </Field>
          <Button type="submit">Filter</Button>
          {action && (
            <Button
              type="button"
              onClick={() => {
                setAction("");
                setActionInput("");
                setOffset(0);
              }}
            >
              Clear
            </Button>
          )}
        </form>
      </Card>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No audit entries" />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Target</Th>
                <Th>Details</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap text-sand-200">{fmtDate(e.ts)}</Td>
                  <Td>{e.actor_email || e.actor_id || "—"}</Td>
                  <Td>
                    <Badge tone="sand">{e.action}</Badge>
                  </Td>
                  <Td className="text-sand-200">
                    {e.target_type ? (
                      <>
                        {e.target_type}
                        {e.target_id && (
                          <span className="ml-1 font-mono text-xs text-sand-500">
                            {e.target_id}
                          </span>
                        )}
                      </>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>
                    {e.meta && Object.keys(e.meta).length > 0 ? (
                      <details>
                        <summary className="cursor-pointer text-xs text-sand-200">view</summary>
                        <pre className="mt-1 max-w-md overflow-auto rounded border border-sand-500/40 bg-sand-900/60 p-2 text-xs text-sand-50">
                          {JSON.stringify(e.meta, null, 2)}
                        </pre>
                      </details>
                    ) : (
                      <span className="text-sand-500">—</span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="mt-4 flex items-center justify-between text-sm text-sand-200">
            <span>{fmtNumber(data.total)} entries</span>
            <div className="flex gap-2">
              <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Previous
              </Button>
              <Button
                size="sm"
                disabled={offset + PAGE >= data.total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
