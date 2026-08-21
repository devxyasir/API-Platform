"use client";

// useApi: run an async fetcher, track {data, error, loading}, and expose reload().
// Re-runs whenever a value in `deps` changes.

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

interface ApiResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): ApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  // Keep the latest fetcher without forcing it into the dependency array.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetcherRef
      .current()
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof ApiError ? e.message : "Something went wrong.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  return { data, error, loading, reload };
}

// useAsyncAction: wrap a mutating call with pending/error state for buttons/forms.
export function useAsyncAction<Args extends unknown[]>(
  action: (...args: Args) => Promise<unknown>,
) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (...args: Args): Promise<boolean> => {
      setPending(true);
      setError(null);
      try {
        await action(...args);
        return true;
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Something went wrong.");
        return false;
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  return { run, pending, error, setError };
}
