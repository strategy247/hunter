-- ============================================================
-- SEC Form D Lead Tracker — Supabase Schema
-- Run this in the Supabase SQL editor after creating your project
-- ============================================================

-- Enable UUID generation
create extension if not exists "pgcrypto";

-- ── Core Leads ────────────────────────────────────────────────────────────────

create table leads (
  id               uuid primary key default gen_random_uuid(),
  cik              text not null,
  accession_no     text unique not null,   -- natural dedup key from EDGAR

  -- From Form D filing
  company_name     text not null,
  filing_date      date,
  state            text,
  city             text,
  amount_raised    numeric,               -- totalAmountSold
  amount_offered   numeric,               -- totalOfferingAmount
  industry         text,
  security_type    text,
  date_first_sale  date,
  num_investors    integer,
  edgar_url        text,

  -- Inferred / enriched fields
  round_name       text,                  -- "Series A", "Series B" etc (inferred from amount or enriched)
  website          text,
  linkedin_url     text,
  description      text,                  -- from TechCrunch or manual

  created_at       timestamptz default now(),
  updated_at       timestamptz default now()
);

-- ── Executives / Related Persons (from Form D) ────────────────────────────────

create table lead_persons (
  id           uuid primary key default gen_random_uuid(),
  lead_id      uuid references leads(id) on delete cascade,
  name         text not null,
  roles        text[],                    -- e.g. {"executiveOfficer", "director"}
  is_executive boolean default false,
  created_at   timestamptz default now()
);

-- ── Investors (enriched — Form D doesn't disclose VC names) ───────────────────

create table lead_investors (
  id             uuid primary key default gen_random_uuid(),
  lead_id        uuid references leads(id) on delete cascade,
  investor_name  text not null,
  is_lead        boolean default false,
  source         text default 'manual'    -- 'techcrunch', 'manual', 'crunchbase'
                 check (source in ('techcrunch', 'manual', 'crunchbase', 'other')),
  created_at     timestamptz default now()
);

-- ── Outreach Tracking ─────────────────────────────────────────────────────────

create type outreach_status as enum (
  'new',
  'reviewing',
  'contacted',
  'responded',
  'interviewing',
  'offer',
  'not_interested',
  'closed_won'
);

create type outreach_type as enum (
  'job',
  'consulting',
  'investor_prospect'
);

create table outreach (
  id              uuid primary key default gen_random_uuid(),
  lead_id         uuid references leads(id) on delete cascade,
  status          outreach_status default 'new',
  outreach_type   outreach_type default 'job',
  contact_name    text,
  contact_title   text,
  contact_email   text,
  contact_linkedin text,
  last_contact_at timestamptz,
  next_followup_at timestamptz,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- One active outreach record per lead (enforce at app level, allow multiples for history)

-- ── Notes ─────────────────────────────────────────────────────────────────────

create table notes (
  id         uuid primary key default gen_random_uuid(),
  lead_id    uuid references leads(id) on delete cascade,
  content    text not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ── Useful Views ──────────────────────────────────────────────────────────────

-- Leads with latest outreach status and lead investor — primary table view
create or replace view leads_summary as
select
  l.id,
  l.company_name,
  l.filing_date,
  l.state,
  l.city,
  l.amount_raised,
  l.amount_offered,
  coalesce(l.amount_raised, l.amount_offered) as best_amount,
  l.round_name,
  l.industry,
  l.num_investors,
  l.edgar_url,
  l.website,
  l.linkedin_url,
  -- latest outreach status
  o.status          as outreach_status,
  o.outreach_type,
  o.contact_name,
  o.last_contact_at,
  o.next_followup_at,
  -- lead investor name (first one flagged as lead)
  li.investor_name  as lead_investor,
  l.created_at,
  l.updated_at
from leads l
left join lateral (
  select * from outreach
  where lead_id = l.id
  order by updated_at desc
  limit 1
) o on true
left join lateral (
  select investor_name from lead_investors
  where lead_id = l.id and is_lead = true
  limit 1
) li on true;

-- ── Indexes ───────────────────────────────────────────────────────────────────

create index on leads (filing_date desc);
create index on leads (state);
create index on leads (amount_raised);
create index on leads (company_name);
create index on outreach (lead_id);
create index on outreach (status);
create index on lead_investors (lead_id);
create index on lead_persons (lead_id);
create index on notes (lead_id);

-- ── Updated_at trigger ────────────────────────────────────────────────────────

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger leads_updated_at
  before update on leads
  for each row execute function set_updated_at();

create trigger outreach_updated_at
  before update on outreach
  for each row execute function set_updated_at();

create trigger notes_updated_at
  before update on notes
  for each row execute function set_updated_at();

-- ── Row Level Security (enable after confirming app works) ────────────────────
-- Uncomment when ready to add Supabase Auth

-- alter table leads enable row level security;
-- alter table outreach enable row level security;
-- alter table notes enable row level security;
-- alter table lead_persons enable row level security;
-- alter table lead_investors enable row level security;
