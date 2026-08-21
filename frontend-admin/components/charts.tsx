"use client";

// Minimal dependency-free charts drawn with inline SVG, palette-only colors.
// Colors resolve to the active theme's sand tokens (rgb(var(--sand-*))), so
// lines and axes track light/dark automatically:
// sand-50 (bright) · sand-200 (sand) · sand-500 (olive).
const TONE_COLOR: Record<string, string> = {
  bright: "rgb(var(--sand-50))",
  sand: "rgb(var(--sand-200))",
  olive: "rgb(var(--sand-500))",
};

const AXIS = "rgb(var(--sand-500))";

export interface Series {
  name: string;
  tone?: "bright" | "sand" | "olive";
  data: number[];
}

export function LineChart({
  series,
  labels,
  height = 200,
  yFormat = (n: number) => String(Math.round(n)),
}: {
  series: Series[];
  labels?: string[];
  height?: number;
  yFormat?: (n: number) => string;
}) {
  const W = 640;
  const H = height;
  const padL = 44;
  const padR = 12;
  const padT = 12;
  const padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const n = Math.max(...series.map((s) => s.data.length), 0);
  const max = Math.max(1, ...series.flatMap((s) => s.data));
  const stepX = n > 1 ? plotW / (n - 1) : 0;

  const x = (i: number) => padL + i * stepX;
  const y = (v: number) => padT + plotH - (v / max) * plotH;

  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  if (!n) {
    return <div className="py-12 text-center text-sm text-sand-500">No data in range.</div>;
  }

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        preserveAspectRatio="none"
        role="img"
      >
        {gridLines.map((g) => {
          const gy = padT + plotH - g * plotH;
          return (
            <g key={g}>
              <line
                x1={padL}
                y1={gy}
                x2={W - padR}
                y2={gy}
                stroke={AXIS}
                strokeOpacity={0.25}
                strokeWidth={1}
              />
              <text x={padL - 8} y={gy + 3} textAnchor="end" fontSize="10" fill={AXIS}>
                {yFormat(max * g)}
              </text>
            </g>
          );
        })}

        {series.map((s) => {
          const color = TONE_COLOR[s.tone || "bright"];
          const pts = s.data.map((v, i) => `${x(i)},${y(v)}`).join(" ");
          const area = `M${x(0)},${padT + plotH} L${pts.split(" ").join(" L")} L${x(
            s.data.length - 1,
          )},${padT + plotH} Z`;
          return (
            <g key={s.name}>
              {s.tone !== "olive" && (
                <path d={area} fill={color} fillOpacity={0.1} stroke="none" />
              )}
              <polyline
                points={pts}
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </g>
          );
        })}

        {labels &&
          labels.map((lab, i) => {
            // Show at most ~6 labels to avoid crowding.
            const every = Math.ceil(labels.length / 6);
            if (i % every !== 0 && i !== labels.length - 1) return null;
            return (
              <text
                key={i}
                x={x(i)}
                y={H - 6}
                textAnchor="middle"
                fontSize="10"
                fill={AXIS}
              >
                {lab}
              </text>
            );
          })}
      </svg>

      {series.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-4">
          {series.map((s) => (
            <div key={s.name} className="flex items-center gap-1.5 text-xs text-sand-200">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: TONE_COLOR[s.tone || "bright"] }}
              />
              {s.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function HBars({
  items,
  formatValue = (n: number) => String(n),
}: {
  items: { label: string; value: number; hint?: string }[];
  formatValue?: (n: number) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  if (!items.length) {
    return <div className="py-8 text-center text-sm text-sand-500">No data.</div>;
  }
  return (
    <div className="space-y-2.5">
      {items.map((it) => (
        <div key={it.label}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="truncate text-sand-200">{it.label}</span>
            <span className="ml-2 shrink-0 text-sand-500">
              {formatValue(it.value)}
              {it.hint ? ` · ${it.hint}` : ""}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-sand-500/20">
            <div
              className="h-full rounded-full bg-sand-200"
              style={{ width: `${(it.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
