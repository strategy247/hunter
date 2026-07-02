import { OutreachStatus } from "./supabase";

export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return "—";
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
  return `$${amount.toLocaleString()}`;
}

export function formatDate(dateStr: string): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric"
    });
  } catch {
    return dateStr;
  }
}

export function statusLabel(status: OutreachStatus | null | undefined): string {
  const map: Record<OutreachStatus, string> = {
    new: "New",
    reviewing: "Reviewing",
    contacted: "Contacted",
    responded: "Responded",
    interviewing: "Interviewing",
    offer: "Offer",
    not_interested: "Not Interested",
    closed_won: "Closed / Won",
  };
  return status ? map[status] ?? status : "New";
}

export function statusColor(status: OutreachStatus | null | undefined): string {
  const map: Record<OutreachStatus, string> = {
    new: "bg-gray-100 text-gray-600",
    reviewing: "bg-blue-100 text-blue-700",
    contacted: "bg-yellow-100 text-yellow-700",
    responded: "bg-purple-100 text-purple-700",
    interviewing: "bg-orange-100 text-orange-700",
    offer: "bg-green-100 text-green-700",
    not_interested: "bg-red-100 text-red-600",
    closed_won: "bg-emerald-100 text-emerald-700",
  };
  return status ? map[status] ?? "bg-gray-100 text-gray-600" : "bg-gray-100 text-gray-600";
}

export function roundBadgeStyle(round: string): React.CSSProperties {
  const map: Record<string, React.CSSProperties> = {
    "Pre-Seed": { background: "#F3F4F6", color: "#6B7280" },    // gray
    "Seed":     { background: "#FEF9C3", color: "#854D0E" },    // yellow
    "Series A": { background: "#DCFCE7", color: "#166534" },    // green
    "Series B": { background: "#DBEAFE", color: "#1E40AF" },    // blue
    "Series C": { background: "#EDE9FE", color: "#5B21B6" },    // purple
    "Series D": { background: "#FCE7F3", color: "#9D174D" },    // pink
    "Series E": { background: "#FEE2E2", color: "#991B1B" },    // red
    "Series F": { background: "#FEF3C7", color: "#92400E" },    // amber
    "Series C+":{ background: "#EDE9FE", color: "#5B21B6" },    // purple (legacy)
  };
  return map[round] ?? { background: "#F3F4F6", color: "#6B7280" };
}
