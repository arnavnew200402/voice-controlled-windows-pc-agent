import { desc } from "drizzle-orm";
import { db } from "@/db";
import { memories, tasks } from "@/db/schema";
import { pendingApprovals } from "@/lib/vox/approvals";
import { probeCloud, routerStatus } from "@/lib/vox/brain";
import { USER_ROOT } from "@/lib/vox/constants";
import { netStatus } from "@/lib/vox/netguard";
import { fsAll, fsTrashed, loadVpc, windowRect } from "@/lib/vox/vpc";

export const dynamic = "force-dynamic";

export async function GET() {
  await probeCloud();
  const [vpc, files, trash, mem, recentTasks] = await Promise.all([
    loadVpc(),
    fsAll(),
    fsTrashed(),
    db.select().from(memories).orderBy(desc(memories.id)).limit(20),
    db.select().from(tasks).orderBy(desc(tasks.updatedAt)).limit(5),
  ]);
  const visible = files.filter((f) => !f.trashed && f.path.toLowerCase().startsWith(USER_ROOT.toLowerCase() + "\\") && !/\\archive\\/i.test(f.path) && !/\\appdata\\|\\\.ssh/i.test(f.path));
  const archive = files.filter((f) => !f.trashed && /\\archive\\/i.test(f.path)).length;
  return Response.json({
    vpc: { ...vpc, rects: Object.fromEntries(vpc.windows.map((w) => [w.id, windowRect(vpc, w)])) },
    files: visible.map((f) => ({ path: f.path, kind: f.kind, link: f.linkTarget })),
    archiveCount: archive,
    trash: trash.map((t) => t.trashedFrom),
    router: routerStatus(),
    net: netStatus(),
    approvals: pendingApprovals(),
    memories: mem.map((m) => m.fact),
    tasks: recentTasks,
  });
}
