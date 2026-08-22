/**
 * Mirrors the backend Pydantic schemas in `backend/app/schemas.py`.
 * Change one, change the other.
 */

export type ContractStatus =
  | "uploaded"
  | "extracted"
  | "needs_review"
  | "clean"
  | "approved"
  | "executed"
  | "superseded"
  | "void";

export type Severity = "error" | "warning";

export interface ExtractedFieldRow {
  field_key: string;
  label: string;
  /** Already masked for sensitive keys. The API never returns a full SSN. */
  value: string | null;
  page: number | null;
  /** False means the extractor never located the label — a different
   *  problem from a label that was found sitting empty. */
  found: boolean;
}

export interface Flag {
  id: string;
  rule_id: string;
  field_key: string;
  page: number | null;
  severity: Severity;
  message: string;
  resolved: boolean;
}

export interface Placement {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  /** "template" when the position was copied from a completed contract. */
  how: "anchor" | "offset" | "template";
}

export interface Summary {
  error_count: number;
  warning_count: number;
  pages_to_fix: number[];
}

export interface Approval {
  id: string;
  contract_id: string;
  approved_by: string;
  approved_at: string;
  error_count_at_approval: number;
  overridden: boolean;
  pages_stamped: number[];
  signature_hash: string | null;
  ip_address: string | null;
  /** The account signed in at the time, when the desk has accounts. */
  signed_in_as: string | null;
}

export interface ContractListItem {
  id: string;
  original_filename: string;
  driver_name: string | null;
  status: ContractStatus;
  page_count: number;
  error_count: number;
  warning_count: number;
  template_name: string | null;
  signature_name: string | null;
  sign_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContractDetail {
  id: string;
  original_filename: string;
  status: ContractStatus;
  page_count: number;
  driver_name: string | null;
  extraction_source: string;
  contract_type: string;
  supersedes_id: string | null;
  superseded_by_id: string | null;
  ssn_masked: string | null;

  /** What the reviewer chose at upload time. */
  template_id: string | null;
  template_name: string | null;
  signature_asset_id: string | null;
  signature_name: string | null;
  sign_date: string | null;
  created_at: string;
  updated_at: string;
  summary: Summary;
  fields: ExtractedFieldRow[];
  flags: Flag[];
  placements: Placement[];
  can_approve: boolean;
  can_execute: boolean;
  signature_ready: boolean;
  approval: Approval | null;
}

export interface ContractPage {
  items: ContractListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ContractQuery {
  status?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface ApproveBody {
  approved_by: string;
  /** Must be true to approve a contract that still has errors. The
   *  approval is then recorded as an override. */
  acknowledge_errors: boolean;
}

/* --- Configuration --- */

export interface FieldSpec {
  field_key: string;
  label: string;
  acroform_name: string | null;
  anchors: string[];
  required: boolean;
  max_gap: number;
  page_hint: number | null;
}

export interface FieldMap {
  contract_types: Record<string, FieldSpec[]>;
}

export interface SignatureConfig {
  mode: "anchor" | "offset";
  anchor_phrase: string;
  dx: number;
  dy: number;
  fallback_to_offset: boolean;
  offset_pages: number[];
  offset_x_frac: number;
  offset_y_frac: number;
  width: number;
  height: number;
  max_stamps: number;
  stamp_date: boolean;
  date_dx: number;
  date_dy: number;
  date_format: string;
  date_font_size: number;
}

export interface CarrierConfig {
  carrier_name: string;
  representative_name: string;
  representative_title: string;
  mc_number: string;
  dot_number: string;
  acroform_fills: Record<string, string>;
  signature_file: string | null;
  placements: Record<string, SignatureConfig>;
  signature_uploaded: boolean;
}

export interface ProbeWidget {
  page: number;
  name: string;
  type: string;
  /** Whether the widget holds a value. The value itself is never returned. */
  has_value: boolean;
}

export interface ProbePage {
  page: number;
  text: string;
}

export interface ProbeResult {
  page_count: number;
  has_acroform: boolean;
  widgets: ProbeWidget[];
  pages: ProbePage[];
}

/* --- Audit --- */

export interface AuditEntry {
  id: string;
  contract_id: string;
  original_filename: string | null;
  driver_name: string | null;
  contract_status: ContractStatus | null;
  approved_by: string;
  approved_at: string;
  error_count_at_approval: number;
  overridden: boolean;
  pages_stamped: number[];
  signature_hash: string | null;
  ip_address: string | null;
  signed_in_as: string | null;
}

export interface AuditPage {
  items: AuditEntry[];
  total: number;
  page: number;
  page_size: number;
}

/* --- Duplicate upload --- */

export interface DuplicateUploadDetail {
  message: string;
  contract_id: string;
  original_filename: string;
  status: ContractStatus;
}

/* --- Signature library --- */

export interface SignatureAsset {
  id: string;
  name: string;
  file_hash: string;
  is_default: boolean;
  created_at: string;
}

/* --- Placement templates --- */

export type MarkKind = "signature" | "date";

export interface TemplateMark {
  id: string;
  kind: MarkKind;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  /** "image", "date_text", or "manual". */
  detected_as: string;
  /** The label printed beside the mark, so a reviewer can recognise it. */
  sample_text: string;
  enabled: boolean;
}

/** A mark as sent back after editing. Without an id it is a new one. */
export interface TemplateMarkInput {
  id?: string | null;
  kind: MarkKind;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  sample_text?: string;
  enabled?: boolean;
}

export interface Template {
  id: string;
  name: string;
  description: string;
  source_filename: string;
  page_count: number;
  page_width: number;
  page_height: number;
  created_at: string;
  updated_at: string;
  marks: TemplateMark[];
  signature_count: number;
  date_count: number;
  pages_marked: number[];
  /** False when nothing is enabled, so it cannot be used to stamp yet. */
  ready: boolean;
}

export interface TemplateListItem {
  id: string;
  name: string;
  description: string;
  source_filename: string;
  page_count: number;
  signature_count: number;
  date_count: number;
  pages_marked: number[];
  ready: boolean;
  created_at: string;
}

export interface TemplateUpdate {
  name?: string;
  description?: string;
  marks?: TemplateMarkInput[];
}

/** What the reviewer chooses when uploading a new contract. */
export interface UploadOptions {
  templateId?: string;
  signatureId?: string;
  /** ISO date, as an HTML date input produces. */
  signDate?: string;
}

/* --- Accounts --- */

export interface AuthUser {
  username: string;
  display_name: string;
  /** Display name if there is one, otherwise the username. */
  label: string;
}

export interface AuthStatus {
  /** False while the desk has no accounts — the single-machine default. */
  login_required: boolean;
  signed_in: boolean;
  user: AuthUser | null;
}

export interface LoginBody {
  username: string;
  password: string;
}
