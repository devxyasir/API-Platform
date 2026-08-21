"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  Badge,
  Button,
  EmptyState,
  ErrorBox,
  Field,
  Input,
  Loading,
  PageHeader,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { fmtDate, fmtRelative } from "@/lib/format";

// Admin key management: keys are created and rotated by users in their own account.
// Here an operator can audit every key across the platform and revoke/delete on abuse.
export default function ApiKeysPage() {
  const [userId, setUserId] = useState("");
  const [filter, setFilter] = useState("");
  const { data: keys, error, loading, reload } = useApi(
    () => api.listKeys(filter ? { user_id: filter } : undefined),
    [filter],
  );
  const [rowBusy, setRowBusy] = useState<string | null>(null);

  async function revoke(id: string) {
    if (!confirm("Revoke this key? Applications using it will stop working immediately.")) return;
    setRowBusy(id);
    try {
      await api.revokeKey(id);
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  async function remove(id: string) {
    if (!confirm("Permanently delete this key? This cannot be undone.")) return;
    setRowBusy(id);
    try {
      await api.deleteKey(id);
      reload();
    } finally {
      setRowBusy(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="API Keys"
        description="Every API key across the platform. Keys are created by users in their own account; operators can revoke or delete them here."
        actions={
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setFilter(userId.trim());
            }}
            className="flex items-end gap-2"
          >
            <Field label="Filter by user id">
              <Input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="usr_…"
                className="w-48"
              />
            </Field>
            <Button type="submit">Filter</Button>
            {filter && (
              <Button
                type="button"
                onClick={() => {
                  setUserId("");
                  setFilter("");
                }}
              >
                Clear
              </Button>
            )}
          </form>
        }
      />

      <ErrorBox message={error} />

      {loading && !keys ? (
        <Loading />
      ) : !keys || keys.length === 0 ? (
        <EmptyState
          title="No API keys"
          hint={filter ? "This user has no keys." : "No keys have been created on the platform yet."}
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Key</Th>
              <Th>User</Th>
              <Th>Scopes</Th>
              <Th>Status</Th>
              <Th>Last used</Th>
              <Th>Created</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id}>
                <Td className="font-medium text-sand-50">{k.name}</Td>
                <Td className="font-mono text-sand-200">{k.key_prefix}…</Td>
                <Td className="font-mono text-xs text-sand-500">{k.user_id}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {k.scopes.map((s) => (
                      <Badge key={s} tone="olive">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </Td>
                <Td>
                  <StatusBadge status={k.status} />
                </Td>
                <Td className="text-sand-200">{fmtRelative(k.last_used_at)}</Td>
                <Td className="text-sand-200">{fmtDate(k.created_at)}</Td>
                <Td>
                  <div className="flex justify-end gap-1.5">
                    {k.status === "active" && (
                      <Button size="sm" loading={rowBusy === k.id} onClick={() => revoke(k.id)}>
                        Revoke
                      </Button>
                    )}
                    <Button size="sm" variant="danger" onClick={() => remove(k.id)}>
                      Delete
                    </Button>
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
