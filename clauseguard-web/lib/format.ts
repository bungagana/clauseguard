export function formatMoney(value: string | number | null | undefined, currency = "IDR"): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return "—";
  try {
    return new Intl.NumberFormat("en-ID", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `${currency} ${n.toLocaleString("en-US")}`;
  }
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value + "T00:00:00");
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** "56 days left" / "ended 10 days ago" / "due today" — days_left can be negative in the API. */
export function formatDaysLeft(daysLeft: number | null | undefined): string {
  if (daysLeft === null || daysLeft === undefined) return "";
  if (daysLeft === 0) return "due today";
  if (daysLeft > 0) return `${daysLeft} day${daysLeft === 1 ? "" : "s"} left`;
  const overdue = Math.abs(daysLeft);
  return `ended ${overdue} day${overdue === 1 ? "" : "s"} ago`;
}

export function humanize(code: string | null | undefined): string {
  if (!code) return "";
  return code.toLowerCase().replace(/_/g, " ");
}

export function titleCase(code: string | null | undefined): string {
  const h = humanize(code);
  return h ? h.charAt(0).toUpperCase() + h.slice(1) : "";
}
