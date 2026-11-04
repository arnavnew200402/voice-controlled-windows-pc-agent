import { resolveApproval } from "@/lib/vox/approvals";

export const dynamic = "force-dynamic";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const b = (await req.json().catch(() => ({}))) as { decision?: string; via?: string; loopbackOverlap?: boolean };
  const decision = b.decision === "approved" ? "approved" : "denied";
  const via = ["voice", "click", "hotkey"].includes(b.via ?? "") ? (b.via as string) : "click";
  const r = resolveApproval(id, decision, via, { loopbackOverlap: !!b.loopbackOverlap });
  return Response.json(r, { status: r.ok ? 200 : 409 });
}
