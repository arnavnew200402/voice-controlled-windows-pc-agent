import { recentAudit } from "@/lib/vox/audit";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({ rows: await recentAudit(150) });
}
