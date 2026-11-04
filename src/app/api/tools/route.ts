import { PACKS, toolManifest } from "@/lib/vox/tools";
import { BUILTIN_PROTECTED, getUserProtected } from "@/lib/vox/policy";

export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({ packs: PACKS, tools: toolManifest(), protected: BUILTIN_PROTECTED, userProtected: getUserProtected() });
}
