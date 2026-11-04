import { stopActive } from "@/lib/vox/engine";

export const dynamic = "force-dynamic";

export async function POST() {
  stopActive("hotkey");
  return Response.json({ ok: true });
}
