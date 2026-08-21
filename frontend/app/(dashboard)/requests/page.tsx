"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fmtDate, fmtMs, fmtNumber } from "@/lib/format";

const STATUSES = ["", "success", "error", "timeout", "rate_limited"];
const PAGE = 50;

export default function RequestsPage() {
  const [status, setStatus] = useState("");
  const [model, setModel] = useState("");
  const [modelInput, setModelInput] = useState("");
  const [offset, setOffset] = useState(0);

  const { data, error, loading } = useApi(
    () => api.listRequests({ status, model, limit: PAGE, offset }),
    [status, model, offset],
  );

  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div>
      <PageHeader
        title="Requests"
        description="Every request that passed through the gateway."
      />

      <Card className="mb-4">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setModel(modelInput.trim());
            setOffset(0);
          }}
        >
          <Field label="Status">
            <Select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
              className="!w-40"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s === "" ? "All statuses" : s.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Model">
            <Input
              value={modelInput}
              onChange={(e) => setModelInput(e.target.value)}
              placeholder="e.g. gpt-4o"
              className="!w-48"
            />
          </Field>
          <Button type="submit" variant="ghost">
            Filter
          </Button>
        </form>
      </Card>

      <ErrorBox message={error} />

      {loading && !data ? (
        <Loading />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No requests found" hint="Try widening your filters or send a request through the gateway." />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Model</Th>
                <Th>Endpoint</Th>
                <Th>Format</Th>
                <Th>Status</Th>
                <Th className="text-right">Code</Th>
                <Th className="text-right">Tokens</Th>
                <Th className="text-right">Latency</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.id} className="transition-colors hover:bg-sand-500/10">
                  <Td>
                    <Link href={`/requests/${r.id}`} className="text-sand-50 hover:underline">
                      {fmtDate(r.started_at)}
                    </Link>
                  </Td>
                  <Td>{r.model || "—"}</Td>
                  <Td className="text-sand-200">{r.endpoint}</Td>
                  <Td className="text-sand-500">{r.api_format}</Td>
                  <Td>
                    <StatusBadge status={r.status} />
                  </Td>
                  <Td className="text-right">{r.status_code}</Td>
                  <Td className="text-right">{fmtNumber(r.total_tokens)}</Td>
                  <Td className="text-right">{fmtMs(r.latency_ms)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>

          <div className="mt-4 flex items-center justify-between text-sm text-sand-200">
            <span>
              {fmtNumber(total)} total · page {page} of {pages}
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                Previous
              </Button>
              <Button
                size="sm"
                disabled={page >= pages}
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
