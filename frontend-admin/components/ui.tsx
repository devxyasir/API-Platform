"use client";

// Night-sands UI kit. Every color here comes from the four-color palette via the
// Tailwind tokens defined in tailwind.config.ts (sand-50 #FAE8B4 / sand-200
// #CBBD93 / sand-500 #80775C / sand-900 #574A24). No colors outside the palette.

import {
  useEffect,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

// ---- Spinner --------------------------------------------------------------
export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cx("animate-spin", className)}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.3" strokeWidth="3" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ---- Button ---------------------------------------------------------------
type ButtonVariant = "primary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
}

export function Button({
  variant = "ghost",
  size = "md",
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const base =
    variant === "primary" ? "btn-primary" : variant === "danger" ? "btn-danger" : "btn-ghost";
  const sz = size === "sm" ? "!px-2.5 !py-1.5 !text-xs" : "";
  return (
    <button className={cx(base, sz, className)} disabled={disabled || loading} {...rest}>
      {loading && <Spinner />}
      {children}
    </button>
  );
}

// ---- Form controls --------------------------------------------------------
export function Field({
  label,
  hint,
  children,
}: {
  label?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div>
      {label && <label className="label">{label}</label>}
      {children}
      {hint && <p className="mt-1 text-xs text-sand-500">{hint}</p>}
    </div>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx("input", props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx("input font-mono", props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cx("input appearance-none cursor-pointer", props.className)}
    />
  );
}

// ---- Card / layout --------------------------------------------------------
export function Card({
  children,
  className,
  title,
  actions,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  actions?: ReactNode;
}) {
  return (
    <div className={cx("card p-4", className)}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-sand-50">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-sand-50">{title}</h1>
        {description && <p className="mt-1 text-sm text-sand-200">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

// ---- StatCard -------------------------------------------------------------
export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="card p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-sand-200">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-sand-50">{value}</div>
      {sub !== undefined && <div className="mt-1 text-xs text-sand-500">{sub}</div>}
    </div>
  );
}

// ---- Badge (4-step tonal scale; the palette has no red/green) --------------
type Tone = "bright" | "sand" | "olive" | "inverted";

const TONES: Record<Tone, string> = {
  // luminous cream outline — the "good/active" tone
  bright: "bg-sand-50/15 text-sand-50 border border-sand-50/35",
  // mid sand — neutral/informational
  sand: "bg-sand-500/25 text-sand-200 border border-sand-500/50",
  // muted olive — disabled/archived/idle
  olive: "bg-transparent text-sand-500 border border-sand-500/45",
  // solid cream — highest attention, stands in for red where a state is "bad"
  inverted: "bg-sand-200 text-sand-900 border border-sand-200 font-semibold",
};

export function Badge({
  tone = "sand",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, Tone> = {
  // good
  success: "bright",
  active: "bright",
  enabled: "bright",
  healthy: "bright",
  ready: "bright",
  ok: "bright",
  up: "bright",
  completed: "bright",
  closed: "bright", // circuit breaker closed = healthy
  // bad -> solid, high attention
  error: "inverted",
  failed: "inverted",
  timeout: "inverted",
  down: "inverted",
  unhealthy: "inverted",
  revoked: "inverted",
  open: "inverted", // circuit breaker open = failing
  // caution -> mid
  rate_limited: "sand",
  degraded: "sand",
  warning: "sand",
  pending: "sand",
  half_open: "sand",
  // idle/muted
  disabled: "olive",
  archived: "olive",
  inactive: "olive",
  unknown: "olive",
  never: "olive",
  // billing & account lifecycle
  trialing: "bright",
  paid: "bright",
  past_due: "sand",
  paused: "sand",
  restricted: "sand",
  cancelled: "olive",
  canceled: "olive",
  expired: "olive",
  void: "olive",
  suspended: "inverted",
  uncollectible: "inverted",
};

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const s = (status || "unknown").toLowerCase();
  const tone = STATUS_TONE[s] ?? "sand";
  return <Badge tone={tone}>{s.replace(/_/g, " ")}</Badge>;
}

// ---- Table ----------------------------------------------------------------
export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-sand-500/35">
      <table className="w-full border-collapse">{children}</table>
    </div>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return <th className={cx("th", className)}>{children}</th>;
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cx("td", className)}>{children}</td>;
}

// ---- Feedback -------------------------------------------------------------
export function ErrorBox({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <div className="rounded-lg border border-sand-200/70 bg-sand-200/10 px-3 py-2 text-sm text-sand-50">
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-sand-500/45 py-12 text-center">
      <p className="text-sm font-medium text-sand-200">{title}</p>
      {hint && <p className="max-w-sm text-xs text-sand-500">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-sand-200">
      <Spinner />
      {label}
    </div>
  );
}

// ---- CopyButton -----------------------------------------------------------
export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (e.g. insecure origin) — ignore */
    }
  };
  return (
    <Button size="sm" variant="ghost" onClick={copy}>
      {copied ? "Copied ✓" : label}
    </Button>
  );
}

// ---- Toggle ---------------------------------------------------------------
export function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50",
        checked ? "bg-sand-50" : "bg-sand-500/50",
      )}
    >
      <span
        className={cx(
          "inline-block h-3.5 w-3.5 transform rounded-full transition-transform",
          checked ? "translate-x-4 bg-sand-900" : "translate-x-1 bg-sand-200",
        )}
      />
    </button>
  );
}

// ---- Modal ----------------------------------------------------------------
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-sand-900/70 p-4 backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-sand-500/50 bg-panel shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-sand-500/35 px-4 py-3">
          <h3 className="text-sm font-semibold text-sand-50">{title}</h3>
          <button
            onClick={onClose}
            className="text-sand-500 transition-colors hover:text-sand-50"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-4 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-sand-500/35 px-4 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Tabs -----------------------------------------------------------------
// Controlled tab strip: the parent owns the active key. Used for the user-detail
// view (§44) and other multi-section pages.
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ key: string; label: ReactNode }>;
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="mb-5 flex flex-wrap gap-1 border-b border-sand-500/35">
      {tabs.map((t) => {
        const on = t.key === active;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={cx(
              "-mb-px rounded-t-lg border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              on
                ? "border-sand-50 text-sand-50"
                : "border-transparent text-sand-500 hover:text-sand-200",
            )}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

// ---- ConfirmModal ---------------------------------------------------------
// A small confirmation dialog for destructive / privileged actions (§51). The parent
// controls `open`; `onConfirm` may be async and the button shows a spinner while it runs.
export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button onClick={onClose}>{cancelLabel}</Button>
          <Button
            variant={destructive ? "danger" : "primary"}
            loading={busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {typeof message === "string" ? (
        <p className="text-sm text-sand-200">{message}</p>
      ) : (
        message
      )}
    </Modal>
  );
}

