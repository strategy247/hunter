/**
 * SourceBadges — shows which sources confirmed a data field.
 *
 * Usage:
 *   <SourceBadges sources={["TC", "VCB"]} />
 *
 * Color coding:
 *   TC  = TechCrunch    → green
 *   VCB = VCBacked.co   → blue
 *   X   = X/Twitter     → black
 *   LI  = LinkedIn      → indigo
 *   M   = Manual        → gray
 */

const SOURCE_CONFIG: Record<string, { label: string; color: string; title: string }> = {
  TC:  { label: "TC",  color: "bg-green-100 text-green-700 border-green-200",   title: "Confirmed by TechCrunch" },
  VCB: { label: "VCB", color: "bg-blue-100 text-blue-700 border-blue-200",      title: "Confirmed by VCBacked.co" },
  X:   { label: "𝕏",   color: "bg-gray-900 text-white border-gray-900",          title: "Confirmed by X/Twitter" },
  LI:  { label: "in",  color: "bg-indigo-100 text-indigo-700 border-indigo-200", title: "LinkedIn (search link)" },
  M:   { label: "M",   color: "bg-gray-100 text-gray-500 border-gray-200",       title: "Manually entered" },
};

interface SourceBadgesProps {
  sources: string[];
  size?: "sm" | "xs";
}

export function SourceBadges({ sources, size = "xs" }: SourceBadgesProps) {
  if (!sources?.length) return null;
  const px = size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-1 py-0 text-[10px]";
  return (
    <span className="inline-flex gap-0.5 items-center">
      {sources.map(s => {
        const config = SOURCE_CONFIG[s] ?? { label: s, color: "bg-gray-100 text-gray-500 border-gray-200", title: s };
        return (
          <span
            key={s}
            title={config.title}
            className={`${px} rounded border font-medium leading-tight cursor-default ${config.color}`}
          >
            {config.label}
          </span>
        );
      })}
    </span>
  );
}

/**
 * ConfidenceBar — visual indicator of enrichment completeness.
 * Score 0–100 based on how many fields are multi-source confirmed.
 */
export function ConfidenceBar({ score }: { score: number | null }) {
  if (score == null) return null;
  const color =
    score >= 70 ? "bg-green-500" :
    score >= 40 ? "bg-yellow-500" :
    "bg-gray-300";
  return (
    <div className="flex items-center gap-2" title={`Enrichment confidence: ${score}/100`}>
      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-[10px] text-gray-400">{score}%</span>
    </div>
  );
}

/**
 * InvestorList — shows investors with source badges and lead indicator.
 * Used in both the summary table (lead investor only) and detail page (full list).
 */
interface Investor {
  investor_name: string;
  is_lead: boolean;
  confirmed_by?: string[];
  source?: string;
}

export function InvestorList({ investors }: { investors: Investor[] }) {
  if (!investors?.length) return <span className="text-gray-400 text-xs">—</span>;
  return (
    <div className="space-y-1.5">
      {investors.map((inv, i) => {
        const sources = inv.confirmed_by?.map(s => {
          const map: Record<string, string> = {
            techcrunch: "TC", vcbacked: "VCB", x: "X", linkedin: "LI", manual: "M"
          };
          return map[s] ?? s.toUpperCase();
        }) ?? (inv.source ? [{ techcrunch: "TC", vcbacked: "VCB", x: "X", manual: "M" }[inv.source] ?? "M"] : []);

        return (
          <div key={i} className="flex items-center gap-2">
            {inv.is_lead && (
              <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 text-[10px] font-semibold rounded uppercase tracking-wide">
                Lead
              </span>
            )}
            <span className="text-sm text-gray-800">{inv.investor_name}</span>
            <SourceBadges sources={sources} />
          </div>
        );
      })}
    </div>
  );
}
