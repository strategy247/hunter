import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

/**
 * POST /api/crm/push
 * Body: { leadId: string, platform: "salesforce" | "hubspot" }
 *
 * Fetches lead + contacts from Supabase and pushes to the chosen CRM.
 * The Python crm.py module handles the actual CRM API calls.
 * This route bridges the Next.js frontend to a lightweight Python microservice,
 * or can call the CRM APIs directly via their JS SDKs if preferred.
 *
 * For now: calls the CRM APIs directly using env vars set in Vercel.
 */

export async function POST(req: NextRequest) {
  const { leadId, platform } = await req.json();

  if (!leadId || !["salesforce", "hubspot"].includes(platform)) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }

  // Fetch lead data
  const { data: lead, error: leadErr } = await supabase
    .from("leads")
    .select("*")
    .eq("id", leadId)
    .single();

  if (leadErr || !lead) {
    return NextResponse.json({ error: "Lead not found" }, { status: 404 });
  }

  // Fetch enriched contacts
  const { data: persons } = await supabase
    .from("lead_persons")
    .select("*")
    .eq("lead_id", leadId)
    .eq("is_executive", true);

  // Fetch outreach status
  const { data: outreach } = await supabase
    .from("outreach")
    .select("*")
    .eq("lead_id", leadId)
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const payload = {
    ...lead,
    outreach_status: outreach?.status ?? "new",
    outreach_type: outreach?.outreach_type ?? "job",
  };

  // Call Python CRM service (or implement JS SDK calls here)
  // For Vercel deployment, you have two options:
  //   A) Deploy the Python crm.py as a separate service (e.g. Railway, Fly.io)
  //   B) Reimplement the CRM API calls in TypeScript below

  const crmServiceUrl = process.env.CRM_SERVICE_URL;
  if (crmServiceUrl) {
    const res = await fetch(`${crmServiceUrl}/push`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lead: payload, contacts: persons, platform }),
    });
    const result = await res.json();
    return NextResponse.json(result);
  }

  // Fallback: return a placeholder until Python service is deployed
  return NextResponse.json({
    success: false,
    message: `CRM_SERVICE_URL not set. Deploy ingestor/crm.py as a service and set the env var, or implement ${platform} JS SDK calls in this route.`,
    lead_name: lead.company_name,
    platform,
  });
}
