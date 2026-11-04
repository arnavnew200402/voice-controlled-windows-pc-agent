import {
  boolean,
  integer,
  jsonb,
  pgTable,
  serial,
  text,
  timestamp,
} from "drizzle-orm/pg-core";

/** Virtual PC file system (sandbox). Paths are normalised Windows paths. */
export const vpcFiles = pgTable("vpc_files", {
  id: serial("id").primaryKey(),
  path: text("path").notNull().unique(),
  kind: text("kind").notNull(), // file | dir
  content: text("content").notNull().default(""),
  linkTarget: text("link_target"), // junction / symlink simulation
  trashed: boolean("trashed").notNull().default(false),
  trashedFrom: text("trashed_from"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

/** Single-row JSON state of the virtual PC (apps, windows, volume...). */
export const vpcState = pgTable("vpc_state", {
  id: integer("id").primaryKey(),
  data: jsonb("data").notNull(),
});

/** Append-only audit log. Never stores secrets (args are redacted). */
export const auditLog = pgTable("audit_log", {
  id: serial("id").primaryKey(),
  ts: timestamp("ts").notNull().defaultNow(),
  turnId: text("turn_id"),
  tool: text("tool").notNull(),
  tier: integer("tier").notNull(),
  argsHash: text("args_hash").notNull(),
  argsRedacted: jsonb("args_redacted").notNull(),
  decision: text("decision").notNull(), // auto | approved | denied | blocked | expired | invalid
  via: text("via"), // voice | click | hotkey | policy | timeout
  ok: boolean("ok").notNull().default(false),
  summary: text("summary").notNull().default(""),
  untrustedDerived: boolean("untrusted_derived").notNull().default(false),
});

/** Every bus event is also persisted here (event ledger). */
export const eventLog = pgTable("event_log", {
  id: serial("id").primaryKey(),
  ts: timestamp("ts").notNull().defaultNow(),
  turnId: text("turn_id"),
  type: text("type").notNull(),
  payload: jsonb("payload").notNull(),
});

export const memories = pgTable("memories", {
  id: serial("id").primaryKey(),
  fact: text("fact").notNull(),
  source: text("source").notNull().default("user"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const settings = pgTable("settings", {
  key: text("key").primaryKey(),
  value: jsonb("value").notNull(),
});

export const tasks = pgTable("tasks", {
  id: text("id").primaryKey(),
  goal: text("goal").notNull(),
  status: text("status").notNull(), // running | paused | done | failed | stopped
  steps: jsonb("steps").notNull(),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});
