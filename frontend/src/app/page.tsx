"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Search, Filter, Download, RefreshCw,
  TrendingUp, Building2, DollarSign, Calendar
} from "lucide-react";
import {
  getLeads, LeadSummary, OutreachStatus, OutreachType
} from "@/lib/supabase";
import { formatCurrency, formatDate, statusColor, statusLabel, roundBadgeStyle } from "@/lib/utils";

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
];

const STATUSES: OutreachStatus[] = [
  "new","reviewing","contacted","responded","interviewing","offer","not_interested","closed_won"
];

const ROUND_NAMES = ["Pre-Seed", "Seed", "Series A", "Series B", "Series C", "Series D", "Series E", "Series F"];

export default function LeadsPage() {
  const router = useRouter();
  const [leads, setLeads] = useState<LeadSummary[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  // Filters
  const [search, setSearch] = useState("");
  const [states, setStates] = useState<string[]>([]);
  const [minAmount, setMinAmount] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [status, setStatus] = useState<OutreachStatus | "">("");
  const [outreachType, setOutreachType] = useState<OutreachType | "">("");
  const [roundName, setRoundName] = useState("");

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    try {
      const { data, count } = await getLeads({
        search: search || undefined,
        states: states.length ? states : undefined,
        minAmount: minAmount ? Number(minAmount) : undefined,
        maxAmount: maxAmount ? Number(maxAmount) : undefined,
        status: status || undefined,
        outreachType: outreachType || undefined,
        roundName: roundName || undefined,
        page,
        pageSize,
      });
      setLeads(data);
      setCount(count);
    } finally {
      setLoading(false);
    }
  }, [search, states, minAmount, maxAmount, status, outreachType, roundName, page]);

  useEffect(() => { fetchLeads(); }, [fetchLeads]);

  const exportCSV = () => {
    const headers = [
      "Company","Filed","State","City","Round","Amount Raised",
      "Lead Investor","Outreach Status","Contact","Last Contact"
    ];
    const rows = leads.map(l => [
      l.company_name, l.filing_date, l.state, l.city,
      l.round_name ?? "", formatCurrency(l.best_amount),
      l.lead_investor ?? "", statusLabel(l.outreach_status),
      l.contact_name ?? "", l.last_contact_at ? formatDate(l.last_contact_at) : "",
    ]);
    const csv = [headers, ...rows].map(r => r.map(c => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `formd_leads_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-screen-xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Hunter Leads</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {count.toLocaleString()} companies · sourced from SEC EDGAR
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={fetchLeads}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              <RefreshCw size={14} /> Refresh
            </button>
            <button
              onClick={exportCSV}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
            >
              <Download size={14} /> Export CSV
            </button>
          </div>
        </div>
      </div>

      {/* Stats bar */}
      <div className="bg-white border-b border-gray-100 px-6 py-3">
        <div className="max-w-screen-xl mx-auto grid grid-cols-4 gap-6 text-sm">
          <StatCard icon={<Building2 size={14}/>} label="Total Leads" value={count.toLocaleString()} />
          <StatCard icon={<TrendingUp size={14}/>} label="Contacted" value={leads.filter(l=>l.outreach_status==="contacted").length.toString()} />
          <StatCard icon={<DollarSign size={14}/>} label="In Progress" value={leads.filter(l=>["responded","interviewing","offer"].includes(l.outreach_status??""  )).length.toString()} />
          <StatCard icon={<Calendar size={14}/>} label="New This Week" value={leads.filter(l=> l.filing_date && new Date(l.filing_date) > new Date(Date.now()-7*864e5)).length.toString()} />
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="max-w-screen-xl mx-auto flex flex-wrap gap-3 items-center">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-2.5 text-gray-400" />
            <input
              className="pl-8 pr-3 py-2 text-sm border border-gray-300 rounded-lg w-52"
              placeholder="Search company..."
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(0); }}
            />
          </div>

          <select
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg"
            value={states[0] ?? ""}
            onChange={e => { setStates(e.target.value ? [e.target.value] : []); setPage(0); }}
          >
            <option value="">All States</option>
            {US_STATES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <select
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg"
            value={roundName}
            onChange={e => { setRoundName(e.target.value); setPage(0); }}
          >
            <option value="">All Rounds</option>
            {ROUND_NAMES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>

          <select
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg"
            value={status}
            onChange={e => { setStatus(e.target.value as OutreachStatus | ""); setPage(0); }}
          >
            <option value="">All Statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>

          <select
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg"
            value={outreachType}
            onChange={e => { setOutreachType(e.target.value as OutreachType | ""); setPage(0); }}
          >
            <option value="">All Types</option>
            <option value="job">Job</option>
            <option value="consulting">Consulting</option>
            <option value="investor_prospect">Investor</option>
          </select>

          <div className="flex gap-1.5 items-center">
            <span className="text-xs text-gray-400"><Filter size={12} className="inline" /> Amount</span>
            <input
              className="px-2 py-2 text-sm border border-gray-300 rounded-lg w-28"
              placeholder="Min $"
              value={minAmount}
              onChange={e => { setMinAmount(e.target.value); setPage(0); }}
            />
            <span className="text-gray-400">–</span>
            <input
              className="px-2 py-2 text-sm border border-gray-300 rounded-lg w-28"
              placeholder="Max $"
              value={maxAmount}
              onChange={e => { setMaxAmount(e.target.value); setPage(0); }}
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="max-w-screen-xl mx-auto px-6 py-4">
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-xs font-medium text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-left">Location</th>
                <th className="px-4 py-3 text-left whitespace-nowrap min-w-[80px]">Round</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3 text-left">Lead Investor</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Contact</th>
                <th className="px-4 py-3 text-left">Filed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-gray-400">Loading…</td></tr>
              ) : leads.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-gray-400">No results. Try adjusting filters.</td></tr>
              ) : leads.map(lead => (
                <tr
                  key={lead.id}
                  className="hover:bg-indigo-50/40 cursor-pointer transition-colors"
                  onClick={() => router.push(`/leads/${lead.id}`)}
                >
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {lead.company_name}
                    {lead.next_followup_at && new Date(lead.next_followup_at) <= new Date() && (
                      <span className="ml-2 inline-block w-1.5 h-1.5 bg-orange-400 rounded-full" title="Follow-up due" />
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{lead.city}, {lead.state}</td>
                  <td className="px-4 py-3">
                    {lead.round_name && (
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap inline-block text-center w-20" style={roundBadgeStyle(lead.round_name)}>
                        {lead.round_name}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 font-mono text-xs">
                    {formatCurrency(lead.best_amount)}
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{lead.lead_investor ?? "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={lead.outreach_status} />
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{lead.contact_name ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{formatDate(lead.filing_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {count > pageSize && (
          <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
            <span>Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, count)} of {count}</span>
            <div className="flex gap-2">
              <button
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
                className="px-3 py-1.5 border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50"
              >Previous</button>
              <button
                disabled={(page + 1) * pageSize >= count}
                onClick={() => setPage(p => p + 1)}
                className="px-3 py-1.5 border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50"
              >Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-gray-400">{icon}</span>
      <span className="text-gray-500">{label}:</span>
      <span className="font-semibold text-gray-800">{value}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: OutreachStatus | null }) {
  if (!status || status === "new") return <span className="text-gray-400 text-xs">New</span>;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColor(status)}`}>
      {statusLabel(status)}
    </span>
  );
}
