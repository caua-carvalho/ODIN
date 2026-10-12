/**
 * Daily briefing payload.
 *
 * These types mirror the frozen backend contract for
 * `GET /api/briefing` exactly — do not rename or invent fields.
 */

export interface BriefingWeather {
  city: string;
  temperature: number;
  apparent: number;
  /** WMO weather interpretation code. */
  code: number;
  description: string;
  temp_max: number;
  temp_min: number;
  /** Probability of precipitation, percent (0–100). */
  precipitation_probability: number;
}

export interface BriefingGitRepo {
  name: string;
  path: string;
  branch: string;
  /** Number of uncommitted changes. */
  changes: number;
  last_commit: string;
  ahead: number;
  behind: number;
}

export interface BriefingRecentFile {
  path: string;
  age_seconds: number;
}

export interface BriefingFiles {
  recent: BriefingRecentFile[];
  todo_count: number;
}

export interface BriefingSystem {
  cpu_percent: number;
  memory_percent: number;
  memory_used: number;
  memory_total: number;
  disk_percent: number;
  disk_used: number;
  disk_total: number;
  load_avg: number[];
  uptime_seconds: number;
}

export interface BriefingRuntime {
  status: string;
  version: string;
  provider: string;
  model: string;
  tools_count: number;
  agent_ready: boolean;
}

export interface BriefingPermissions {
  pending: number;
  high_risk: number;
}

export interface BriefingConversation {
  id: string;
  title: string;
  updated_at: string;
}

export interface BriefingResponse {
  should_show: boolean;
  boot_time: number;
  /** ISO timestamp of when the briefing was generated. */
  generated_at: string;
  weather: BriefingWeather | null;
  /** Array of repos; individual entries may be null. */
  git: (BriefingGitRepo | null)[];
  files: BriefingFiles;
  system: BriefingSystem;
  runtime: BriefingRuntime;
  permissions: BriefingPermissions;
  conversations: BriefingConversation[];
}

export interface BriefingSummaryResponse {
  summary: string | null;
}

export interface BriefingAckResponse {
  acknowledged: boolean;
  boot_time: number;
}
