export type JobStatus =
  | "queued"
  | "parsing"
  | "translating"
  | "rebuilding"
  | "validating"
  | "completed"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  status: JobStatus;
  stage: string | null;
  progress: number;
  source_language: string;
  target_language: string;
  style: string | null;
  domain: string | null;
  total_units: number | null;
  done_units: number | null;
  error_code: string | null;
  error_summary: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  file_name: string | null;
  has_result: boolean;
  has_report: boolean;
}

export interface Attachment {
  id: string;
  original_filename: string;
  size_bytes: number;
  mime_type: string;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  status: "complete" | "stopped" | "error";
  created_at: string;
  attachments: Attachment[];
}

export interface ChatSummary {
  id: string;
  title: string;
  last_message: string | null;
  message_count: number;
  updated_at: string;
}

export interface ChatDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface Glossary {
  id: string;
  name: string;
  source_language: string;
  target_language: string;
  term_count: number;
  created_at: string;
}

export interface Term {
  id: string;
  glossary_id: string;
  source_term: string;
  target_term: string;
  note: string | null;
}

export interface GlossaryDetail extends Glossary {
  terms: Term[];
}

export interface Meta {
  target_languages: { code: string; label: string }[];
  styles: { code: string; label: string }[];
  domains: { code: string; label: string }[];
  max_upload_mb: number;
  default_target_language: string;
}

export interface SettingsPayload {
  values: Record<string, string | number | boolean>;
  defaults: Record<string, string | number | boolean>;
  editable: string[];
}

export interface Report {
  units: number;
  translated: number;
  failed: { id: string; reason: string }[];
  hard_checks_ok: boolean;
  checks: { check: string; ok: boolean; source?: unknown; output?: unknown }[];
  quality: {
    ratios: Record<string, number>;
    empty: string[];
    number_mismatch: string[];
    placeholder_mismatch: string[];
  };
  budget: { slot_ctx: number; text_budget: number; output_cap: number; batches: number };
  duration_seconds: number;
}

export interface UploadedFile {
  id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
}
