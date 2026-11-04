import { classifyCommand, getTool } from "@/lib/vox/tools";
import { classify, normalizePath, PathError, TIER_NAME } from "@/lib/vox/policy";
import { resolveLinks } from "@/lib/vox/vpc";

export const dynamic = "force-dynamic";

/** Dry-run: what tier would this path/tool get? Never executes anything. */
export async function POST(req: Request) {
  const b = (await req.json().catch(() => ({}))) as { tool?: string; path?: string; mode?: "read" | "write" | "delete"; command?: string };
  const tool = getTool(b.tool ?? "create_file");
  if (!tool) return Response.json({ tier: 0, label: "UNKNOWN_TOOL", reasons: ["Unknown tools are rejected"] });
  const pathArgs: { arg: string; value: string; mode: "read" | "write" | "delete" }[] = [];
  let normalized: string | null = null;
  let resolved: string | null = null;
  let error: string | null = null;
  if (b.path) {
    const mode = b.mode ?? "write";
    pathArgs.push({ arg: "path", value: b.path, mode });
    try {
      normalized = normalizePath(b.path);
      resolved = await resolveLinks(normalized);
      if (resolved !== normalized) pathArgs.push({ arg: "path", value: resolved, mode });
    } catch (e) {
      error = e instanceof PathError ? `${e.code}: ${e.message}` : String(e);
    }
  }
  const extraTier = b.command ? classifyCommand(b.command) : undefined;
  const c = classify({ tool: tool.name, baseTier: tool.tier, pathArgs, extraTier });
  return Response.json({ tier: c.tier, label: TIER_NAME[c.tier], reasons: c.reasons, normalized, resolved, error, baseTier: tool.tier });
}
