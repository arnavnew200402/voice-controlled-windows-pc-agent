import { routerStatus, setMode } from "@/lib/vox/brain";
import { setNetworkUp, netStatus } from "@/lib/vox/netguard";
import { probeCloud } from "@/lib/vox/brain";

export const dynamic = "force-dynamic";

/** POST {mode} sets requested mode; POST {networkUp} toggles the simulated connectivity. */
export async function POST(req: Request) {
  const b = (await req.json().catch(() => ({}))) as { mode?: string; networkUp?: boolean };
  if (b.mode && ["offline", "auto", "online"].includes(b.mode)) setMode(b.mode as "offline" | "auto" | "online");
  if (typeof b.networkUp === "boolean") {
    setNetworkUp(b.networkUp);
    await probeCloud(true);
  }
  return Response.json({ router: routerStatus(), net: netStatus() });
}
