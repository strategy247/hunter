"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, ExternalLink, Linkedin, Globe, Plus, Save,
  User, Users, DollarSign, FileText, Building2
} from "lucide-react";
import {
  getLead, getLeadPersons, getLeadInvestors, getNotes, getOutreach,
  addNote, upsertOutreach, addInvestor,
  LeadDetail, LeadPerson, LeadInvestor, Note, Outreach,
  OutreachStatus, OutreachType,
} from "@/lib/supabase";
import { formatCurrency, formatDate, statusColor, statusLabel } from "@/lib/utils";

const STATUSES: { value: OutreachStatus; label: string }[] = [
  { value: "new", label: "New" },
  { value: "reviewing", label: "Reviewing" },
  { value: "contacted", label: "Contacted" },
  { value: "responded", label: "Responded" },
  { value: "interviewing", label: "Interviewing" },
  { value: "offer", label: "Offer" },
  { value: "not_interested", label: "Not Interested" },
  { value: "closed_won", label: "Closed / Won" },
];

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [persons, setPersons] = useState<LeadPerson[]>([]);
  const [investors, setInvestors] = useState<LeadInvestor[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [outreach, setOutreach] = useState<Outreach | null>(null);
  const [loading, setLoading] = useState(true);

  // Outreach form state
  const [outreachForm, setOutreachForm] = useState<{
    status: OutreachStatus;
    outreach_type: OutreachType;
    contact_name: string;
    contact_title: string;
    contact_email: string;
    contact_linkedin: string;
    next_followup_at: string;
  }>({
    status: "new",
    outreach_type: "job",
    contact_name: "",
    contact_title: "",
    contact_email: "",
    contact_linkedin: "",
    next_followup_at: "",
  });
  const [savingOutreach, setSavingOutreach] = useState(false);

  // Notes
  const [newNote, setNewNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  // Investor enrichment
  const [newInvestorName, setNewInvestorName] = useState("");
  const [newInvestorIsLead, setNewInvestorIsLead] = useState(false);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      getLead(id),
      getLeadPersons(id),
      getLeadInvestors(id),
      getNotes(id),
      getOutreach(id),
    ]).then(([lead, persons, investors, notes, outreach]) => {
      setLead(lead);
      setPersons(persons);
      setInvestors(investors);
      setNotes(notes);
      setOutreach(outreach);
      if (outreach) {
        setOutreachForm({
          status: outreach.status,
          outreach_type: outreach.outreach_type,
          contact_name: outreach.contact_name ?? "",
          contact_title: outreach.contact_title ?? "",
          contact_email: outreach.contact_email ?? "",
          contact_linkedin: outreach.contact_linkedin ?? "",
          next_followup_at: outreach.next_followup_at?.slice(0,10) ?? "",
        });
      }
      setLoading(false);
    });
  }, [id]);

  const saveOutreach = async () => {
    if (!id) return;
    setSavingOutreach(true);
    const updated = await upsertOutreach(id, {
      ...outreachForm,
      last_contact_at: outreachForm.contact_name ? new Date().toISOString() : undefined,
    });
    setOutreach(updated);
    setSavingOutreach(false);
  };

  const saveNote = async () => {
    if (!id || !newNote.trim()) return;
    setSavingNote(true);
    const note = await addNote(id, newNote.trim());
    setNotes(prev => [note, ...prev]);
    setNewNote("");
    setSavingNote(false);
  };

  const saveInvestor = async () => {
    if (!id || !newInvestorName.trim()) return;
    const inv = await addInvestor(id, newInvestorName.trim(), newInvestorIsLead);
    setInvestors(prev => [inv, ...prev]);
    setNewInvestorName("");
    setNewInvestorIsLead(false);
  };

  if (loading) return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">Loading…</div>;
  if (!lead) return <div className="p-8 text-gray-500">Lead not found.</div>;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-screen-lg mx-auto">
          <button
            onClick={() => router.push("/")}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-3"
          >
            <ArrowLeft size={14} /> Back to Leads
          </button>
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900">{lead.company_name}</h1>
              <p className="text-sm text-gray-500 mt-1">
                {lead.city}, {lead.state} · Filed {formatDate(lead.filing_date ?? "")}
                {lead.round_name && (
                  <span className="ml-2 px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full text-xs font-medium">
                    {lead.round_name}
                  </span>
                )}
              </p>
            </div>
            <div className="flex gap-2">
              {lead.website && (
                <a href={lead.website} target="_blank" rel="noreferrer"
                   className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                  <Globe size={13}/> Website
                </a>
              )}
              {lead.linkedin_url && (
                <a href={lead.linkedin_url} target="_blank" rel="noreferrer"
                   className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                  <Linkedin size={13}/> LinkedIn
                </a>
              )}
              <a href={lead.edgar_url} target="_blank" rel="noreferrer"
                 className="flex items-center gap-1 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
                <ExternalLink size={13}/> EDGAR
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-screen-lg mx-auto px-6 py-6 grid grid-cols-3 gap-6">

        {/* Left column — funding, people, investors */}
        <div className="col-span-2 space-y-5">

          {/* Funding Summary */}
          <Section icon={<DollarSign size={15}/>} title="Funding">
            <div className="grid grid-cols-3 gap-4">
              <Stat label="Amount Raised" value={formatCurrency(lead.amount_raised)} />
              <Stat label="Amount Offered" value={formatCurrency(lead.amount_offered)} />
              <Stat label="Investors" value={lead.num_investors?.toString() ?? "—"} />
              <Stat label="First Sale" value={lead.date_first_sale ? formatDate(lead.date_first_sale) : "—"} />
              <Stat label="Security Type" value={lead.security_type ?? "—"} />
              <Stat label="Industry" value={lead.industry ?? "—"} />
            </div>
          </Section>

          {/* Investors */}
          <Section icon={<Building2 size={15}/>} title="Investors">
            <p className="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2 mb-3">
              Form D does not disclose investor names. Add them manually or from TechCrunch.
            </p>
            {investors.length > 0 && (
              <div className="space-y-2 mb-3">
                {investors.map(inv => (
                  <div key={inv.id} className="flex items-center gap-2 text-sm">
                    {inv.is_lead && <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 text-xs rounded font-medium">Lead</span>}
                    <span className="text-gray-800">{inv.investor_name}</span>
                    <span className="text-gray-400 text-xs">· {inv.source}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2 items-center">
              <input
                className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg"
                placeholder="Investor / VC name"
                value={newInvestorName}
                onChange={e => setNewInvestorName(e.target.value)}
              />
              <label className="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="checkbox" checked={newInvestorIsLead} onChange={e => setNewInvestorIsLead(e.target.checked)} />
                Lead
              </label>
              <button
                onClick={saveInvestor}
                className="flex items-center gap-1 px-3 py-1.5 text-sm bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200"
              >
                <Plus size={12}/> Add
              </button>
            </div>
          </Section>

          {/* Executives */}
          <Section icon={<Users size={15}/>} title={`Executives / Related Persons (${persons.length})`}>
            {persons.length === 0 ? (
              <p className="text-sm text-gray-400">No related persons found in filing.</p>
            ) : (
              <div className="space-y-2">
                {persons.map(p => (
                  <div key={p.id} className="flex items-start gap-3">
                    <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center text-gray-400 flex-shrink-0">
                      <User size={13}/>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-800">{p.name}</p>
                      <p className="text-xs text-gray-400">{p.roles.join(", ")}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* Notes */}
          <Section icon={<FileText size={15}/>} title="Notes">
            <div className="mb-3">
              <textarea
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg resize-none"
                rows={3}
                placeholder="Add a note about this company…"
                value={newNote}
                onChange={e => setNewNote(e.target.value)}
              />
              <button
                onClick={saveNote}
                disabled={savingNote || !newNote.trim()}
                className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40"
              >
                <Plus size={13}/> {savingNote ? "Saving…" : "Add Note"}
              </button>
            </div>
            {notes.length === 0 ? (
              <p className="text-sm text-gray-400">No notes yet.</p>
            ) : (
              <div className="space-y-3">
                {notes.map(n => (
                  <div key={n.id} className="bg-gray-50 rounded-lg px-3 py-2.5">
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{n.content}</p>
                    <p className="text-xs text-gray-400 mt-1">{formatDate(n.created_at)}</p>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>

        {/* Right column — outreach tracking */}
        <div className="space-y-5">
          <Section icon={<User size={15}/>} title="Outreach">
            <div className="space-y-3">
              <Field label="Status">
                <select
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg"
                  value={outreachForm.status}
                  onChange={e => setOutreachForm(f => ({ ...f, status: e.target.value as OutreachStatus }))}
                >
                  {STATUSES.map(s => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </Field>

              <Field label="Outreach Type">
                <select
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg"
                  value={outreachForm.outreach_type}
                  onChange={e => setOutreachForm(f => ({ ...f, outreach_type: e.target.value as OutreachType }))}
                >
                  <option value="job">Job</option>
                  <option value="consulting">Consulting</option>
                  <option value="investor_prospect">Investor Prospect</option>
                </select>
              </Field>

              <Field label="Contact Name">
                <input
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg"
                  value={outreachForm.contact_name}
                  onChange={e => setOutreachForm(f => ({ ...f, contact_name: e.target.value }))}
                  placeholder="Jane Smith"
                />
              </Field>

              <Field label="Title">
                <input
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg"
                  value={outreachForm.contact_title}
                  onChange={e => setOutreachForm(f => ({ ...f, contact_title: e.target.value }))}
                  placeholder="CPO / CEO"
                />
              </Field>

              <Field label="Email">
                <input
                  type="email"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg"
                  value={outreachForm.contact_email}
                  onChange={e => setOutreachForm(f => ({ ...f, contact_email: e.target.value }))}
                  placeholder="jane@company.com"
                />
              </Field>

              <Field label="LinkedIn">
                <input
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg"
                  value={outreachForm.contact_linkedin}
                  onChange={e => setOutreachForm(f => ({ ...f, contact_linkedin: e.target.value }))}
                  placeholder="linkedin.com/in/..."
                />
              </Field>

              <Field label="Follow-up Date">
                <input
                  type="date"
                  className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg"
                  value={outreachForm.next_followup_at}
                  onChange={e => setOutreachForm(f => ({ ...f, next_followup_at: e.target.value }))}
                />
              </Field>

              <button
                onClick={saveOutreach}
                disabled={savingOutreach}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40"
              >
                <Save size={13}/> {savingOutreach ? "Saving…" : "Save Outreach"}
              </button>

              {outreach && (
                <p className="text-xs text-gray-400 text-center">
                  Last updated {formatDate(outreach.updated_at)}
                </p>
              )}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-700 mb-4">
        <span className="text-gray-400">{icon}</span> {title}
      </h2>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className="text-sm font-medium text-gray-800">{value}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  );
}
