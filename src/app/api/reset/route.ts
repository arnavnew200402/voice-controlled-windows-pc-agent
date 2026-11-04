import { resetRouter } from "@/lib/vox/brain";
import { resetNetCounters, setNetworkUp } from "@/lib/vox/netguard";
import { resetVpc } from "@/lib/vox/vpc";

export const dynamic = "force-dynamic";

export async function POST() {
  await resetVpc();
  resetRouter();
  setNetworkUp(true);
  resetNetCounters();
  return Response.json({ ok: true });
}
