-- ============================================================
-- Migration: Add additional Form D fields to leads table
-- Run in Supabase SQL editor
-- ============================================================

alter table leads
  add column if not exists phone              text,
  add column if not exists street1            text,
  add column if not exists street2            text,
  add column if not exists zip_code           text,
  add column if not exists jurisdiction_inc   text,
  add column if not exists entity_type        text,
  add column if not exists year_inc           text,
  add column if not exists revenue_range      text,
  add column if not exists federal_exemptions text,
  add column if not exists is_amendment       boolean default false,
  add column if not exists sic_code           text,
  add column if not exists min_investment     numeric,
  add column if not exists has_non_accredited boolean default false,
  add column if not exists num_non_accredited integer,
  add column if not exists sales_commissions  numeric,
  add column if not exists finders_fee        numeric;

-- Update leads_summary view to include new fields
-- (drop first: create-or-replace can only append columns, and these are inserted mid-list)
drop view if exists leads_summary;
create view leads_summary as
select
  l.id,
  l.company_name,
  l.filing_date,
  l.state,
  l.city,
  l.street1,
  l.street2,
  l.zip_code,
  l.phone,
  l.amount_raised,
  l.amount_offered,
  coalesce(l.amount_raised, l.amount_offered) as best_amount,
  l.round_name,
  l.industry,
  l.sic_code,
  l.entity_type,
  l.jurisdiction_inc,
  l.year_inc,
  l.revenue_range,
  l.federal_exemptions,
  l.is_amendment,
  l.min_investment,
  l.has_non_accredited,
  l.num_investors,
  l.edgar_url,
  l.website,
  l.linkedin_url,
  l.x_url,
  l.enrichment_sources,
  l.enrichment_confidence,
  l.article_urls,
  -- latest outreach status
  o.status          as outreach_status,
  o.outreach_type,
  o.contact_name,
  o.last_contact_at,
  o.next_followup_at,
  -- lead investor name
  li.investor_name  as lead_investor,
  -- all investor names as array
  inv_all.investor_names,
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
) li on true
left join lateral (
  select array_agg(investor_name order by is_lead desc) as investor_names
  from lead_investors
  where lead_id = l.id
) inv_all on true;
