import { runRedTeam } from "@/lib/vox/redteam";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

/** Runs the red-team suite against the sandbox (resets the virtual PC). */
export async function POST() {
  return Response.json(await runRedTeam());
}
