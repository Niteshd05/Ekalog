export const nf = new Intl.NumberFormat("en-IN");

export function compact(n: number) {
  if (n >= 1e12) return (n / 1e12).toFixed(1) + " T";
  if (n >= 1e9) return (n / 1e9).toFixed(1) + " B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + " M";
  if (n >= 1e4) return (n / 1e3).toFixed(1) + " K";
  return nf.format(Math.round(n));
}

export function bytes(n: number) {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

export function clock(ms: number) {
  if (!ms) return "-";
  const d = new Date(ms);
  return d.toISOString().slice(11, 19);
}

export const CLASS_NAMES: Record<number, string> = {
  0: "Base Event",
  2004: "Detection Finding",
  3002: "Authentication",
  4001: "Network Activity",
  4002: "HTTP Activity",
  4003: "DNS Activity",
};

export const SEVERITY: Record<number, { label: string; tone: string }> = {
  0: { label: "Unknown", tone: "text-faint" },
  1: { label: "Info", tone: "text-muted" },
  2: { label: "Low", tone: "text-cyan" },
  3: { label: "Medium", tone: "text-amber" },
  4: { label: "High", tone: "text-rose" },
  5: { label: "Critical", tone: "text-rose" },
  6: { label: "Fatal", tone: "text-rose" },
};

export function cls(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}
