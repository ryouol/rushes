export type User = { id: string; name: string; email: string };
export type Workspace = {
  id: string;
  name: string;
  role: "owner" | "editor" | "viewer";
  balance_milli: number;
};
export type Project = {
  id: string;
  name: string;
  description: string;
  created_at: string;
};
export type OrganizationCategory = {
  id: string;
  name: string;
  asset_count: number;
};
export type ProjectOrganization = {
  categories: OrganizationCategory[];
  category_total: number;
  has_more: boolean;
  total_assets: number;
  categorized_assets: number;
  uncategorized_assets: number;
  processing_assets: number;
  partial_assets: number;
  not_analyzed_assets: number;
  analysis_configured: boolean;
};
export type AssetOrganization = {
  state: "processing" | "partial" | "organized" | "not_analyzed";
  categories: { id: string; name: string; evidence_count: number }[];
  category_total: number;
  has_more: boolean;
  run_id: string | null;
};
export type Asset = {
  id: string;
  project_id: string;
  name: string;
  relative_path: string;
  import_relative_path: string;
  duplicate_of_id: string | null;
  status: string;
  error: string | null;
  duration_us: number | null;
  can_retry: boolean;
  has_preview: boolean;
  has_thumbnail: boolean;
  source_size: number;
  fingerprint: string | null;
  organization: AssetOrganization;
  timelines?: {
    id: string;
    kind: string;
    details: {
      source_timecode: string | null;
      average_rate: string;
      constant_frame_rate: boolean;
      width: number;
      height: number;
      time_base: string;
      rotation: number;
    };
  }[];
};
export type Observation = {
  id: string;
  asset_id: string;
  kind: string;
  start_us: number;
  end_us: number;
  proposed_start_us: number;
  proposed_end_us: number;
  description: string;
  producer: string;
  model: string;
  uncertainty: string;
  review_status: string;
  version: number;
};
export type Job = {
  id: string;
  project_id: string;
  asset_id: string | null;
  kind: string;
  state: string;
  stage: string;
  progress: number;
  error: string | null;
  updated_at: string;
};
export type Collection = {
  id: string;
  name: string;
  instructions: string;
  saved_query: string | null;
};
export type CollectionItem = {
  id: string;
  asset_id: string;
  asset_name: string;
  start_us: number | null;
  end_us: number | null;
  note: string;
};
export type SearchResult = {
  asset_id: string;
  asset_name: string;
  start_us: number;
  end_us: number;
  processing_status: string;
  has_thumbnail: boolean;
  evidence: {
    observation_id: string;
    description: string;
    kind: string;
    start_us: number;
    end_us: number;
  }[];
};
export type ExportPreview = {
  id: string;
  kind: string;
  output_folder: string;
  estimated_bytes: number;
  entries: {
    source_name: string;
    filename: string;
    start_us: number;
    end_us: number;
    mode: string;
  }[];
  notice: string;
};
export type ExportRecord = {
  id: string;
  kind: string;
  state: string;
  name: string;
  created_at: string;
  output_path: string | null;
  provenance: { outputs?: { output: string; bytes: number }[] };
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export function apiErrorMessage(
  body: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = body.detail;
  let message: unknown = detail;
  if (Array.isArray(detail)) {
    message = detail
      .flatMap((entry) =>
        entry && typeof entry.msg === "string" ? [entry.msg] : [],
      )
      .join(". ");
  } else if (detail && typeof detail === "object" && "reason" in detail) {
    message = detail.reason;
  }
  if (message === "LOGIN_BAD_CREDENTIALS")
    return "Email or password is incorrect.";
  if (message === "REGISTER_USER_ALREADY_EXISTS")
    return "An account already uses this email. Try signing in.";
  return typeof message === "string" && message ? message : fallback;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(options.body instanceof URLSearchParams
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(apiErrorMessage(body), response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function elapsed(us: number) {
  const value = Math.max(0, Math.floor(us / 1000000));
  return `${Math.floor(value / 3600)
    .toString()
    .padStart(2, "0")}:${Math.floor((value / 60) % 60)
    .toString()
    .padStart(2, "0")}:${(value % 60).toString().padStart(2, "0")}`;
}

export type SearchResponse = {
  mode?: "hybrid" | "keyword";
  results: SearchResult[];
  notice: string | null;
  incomplete_processing: boolean;
};
