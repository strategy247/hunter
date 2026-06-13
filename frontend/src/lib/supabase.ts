import { createClient } from "@supabase/supabase-js";

export type OutreachStatus =
  | "new"
  | "reviewing"
  | "contacted"
  | "responded"
  | "interviewing"
  | "offer"
  | "not_interested"
  | "closed_won";

export type OutreachType = "job" | "consulting" | "investor_prospect";

export interface LeadSummary {
  id: string;
  company_name: string;
  filing_date: string;
  state: string;
  city: string;
  amount_raised: number | null;
  amount_offered: number | null;
  best_amount: number | null;
  round_name: string | null;
  industry: string | null;
  num_investors: number | null;
  edgar_url: string;
  website: string | null;
  linkedin_url: string | null;
  outreach_status: OutreachStatus | null;
  outreach_type: OutreachType | null;
  contact_name: string | null;
  last_contact_at: string | null;
  next_followup_at: string | null;
  lead_investor: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadDetail extends LeadSummary {
  description: string | null;
  security_type: string | null;
  date_first_sale: string | null;
  cik: string;
  accession_no: string;
}

export interface LeadPerson {
  id: string;
  name: string;
  roles: string[];
  is_executive: boolean;
}

export interface LeadInvestor {
  id: string;
  investor_name: string;
  is_lead: boolean;
  source: string;
}

export interface Note {
  id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface Outreach {
  id: string;
  status: OutreachStatus;
  outreach_type: OutreachType;
  contact_name: string | null;
  contact_title: string | null;
  contact_email: string | null;
  contact_linkedin: string | null;
  last_contact_at: string | null;
  next_followup_at: string | null;
  created_at: string;
  updated_at: string;
}

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// ── Query helpers ─────────────────────────────────────────────────────────────

export async function getLeads(filters: {
  states?: string[];
  minAmount?: number;
  maxAmount?: number;
  status?: OutreachStatus;
  outreachType?: OutreachType;
  roundName?: string;
  search?: string;
  page?: number;
  pageSize?: number;
}): Promise<{ data: LeadSummary[]; count: number }> {
  const {
    states, minAmount, maxAmount, status, outreachType,
    roundName, search, page = 0, pageSize = 50,
  } = filters;

  let query = supabase
    .from("leads_summary")
    .select("*", { count: "exact" })
    .order("filing_date", { ascending: false })
    .range(page * pageSize, (page + 1) * pageSize - 1);

  if (states?.length) query = query.in("state", states);
  if (minAmount) query = query.gte("best_amount", minAmount);
  if (maxAmount) query = query.lte("best_amount", maxAmount);
  if (status) query = query.eq("outreach_status", status);
  if (outreachType) query = query.eq("outreach_type", outreachType);
  if (roundName) query = query.eq("round_name", roundName);
  if (search) query = query.ilike("company_name", `%${search}%`);

  const { data, count, error } = await query;
  if (error) throw error;
  return { data: data ?? [], count: count ?? 0 };
}

export async function getLead(id: string): Promise<LeadDetail | null> {
  const { data, error } = await supabase
    .from("leads")
    .select("*")
    .eq("id", id)
    .single();
  if (error) throw error;
  return data;
}

export async function getLeadPersons(leadId: string): Promise<LeadPerson[]> {
  const { data, error } = await supabase
    .from("lead_persons")
    .select("*")
    .eq("lead_id", leadId);
  if (error) throw error;
  return data ?? [];
}

export async function getLeadInvestors(leadId: string): Promise<LeadInvestor[]> {
  const { data, error } = await supabase
    .from("lead_investors")
    .select("*")
    .eq("lead_id", leadId)
    .order("is_lead", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

export async function getNotes(leadId: string): Promise<Note[]> {
  const { data, error } = await supabase
    .from("notes")
    .select("*")
    .eq("lead_id", leadId)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

export async function addNote(leadId: string, content: string): Promise<Note> {
  const { data, error } = await supabase
    .from("notes")
    .insert({ lead_id: leadId, content })
    .select()
    .single();
  if (error) throw error;
  return data;
}

export async function getOutreach(leadId: string): Promise<Outreach | null> {
  const { data, error } = await supabase
    .from("outreach")
    .select("*")
    .eq("lead_id", leadId)
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data;
}

export async function upsertOutreach(
  leadId: string,
  updates: Partial<Outreach> & { status: OutreachStatus }
): Promise<Outreach> {
  const existing = await getOutreach(leadId);
  if (existing) {
    const { data, error } = await supabase
      .from("outreach")
      .update({ ...updates, updated_at: new Date().toISOString() })
      .eq("id", existing.id)
      .select()
      .single();
    if (error) throw error;
    return data;
  } else {
    const { data, error } = await supabase
      .from("outreach")
      .insert({ lead_id: leadId, ...updates })
      .select()
      .single();
    if (error) throw error;
    return data;
  }
}

export async function addInvestor(
  leadId: string,
  investorName: string,
  isLead: boolean,
  source: string = "manual"
): Promise<LeadInvestor> {
  const { data, error } = await supabase
    .from("lead_investors")
    .insert({ lead_id: leadId, investor_name: investorName, is_lead: isLead, source })
    .select()
    .single();
  if (error) throw error;
  return data;
}
