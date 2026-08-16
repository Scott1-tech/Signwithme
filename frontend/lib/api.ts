/**
 * The only place that talks to the backend. No inline fetch in components.
 *
 * Requests go to a relative `/api/...`, which `next.config.ts` rewrites to
 * the FastAPI server on 127.0.0.1:8000. Same origin, so there is no CORS
 * preflight in development and nothing to configure.
 */

import type {
  ApproveBody,
  AuditPage,
  CarrierConfig,
  ContractDetail,
  ContractPage,
  ContractQuery,
  DuplicateUploadDetail,
  FieldMap,
  ProbeResult,
  SignatureConfig,
} from "@/lib/types";

export const API_BASE = "/api";

/**
 * An error carrying what the API actually said, so the UI can show a
 * message the reviewer can act on rather than "something went wrong".
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** The existing contract, when an upload was rejected as a duplicate. */
  get duplicate(): DuplicateUploadDetail | null {
    const detail = this.detail;
    if (
      this.status === 409 &&
      detail &&
      typeof detail === "object" &&
      "contract_id" in detail
    ) {
      return detail as DuplicateUploadDetail;
    }
    return null;
  }
}

function messageFromDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors.
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    const body = await response.json();
    detail = (body as { detail?: unknown }).detail ?? body;
  } catch {
    detail = undefined;
  }
  const fallback =
    response.status === 404
      ? "Not found."
      : `The server returned ${response.status}.`;
  return new ApiError(response.status, messageFromDetail(detail, fallback), detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(
      0,
      "Could not reach the backend. Is it running on 127.0.0.1:8000?",
    );
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;

  const type = response.headers.get("content-type") ?? "";
  if (type.includes("application/json")) return (await response.json()) as T;
  return (await response.text()) as T;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

/* --- Contracts --- */

export const contractsApi = {
  list(params: ContractQuery = {}): Promise<ContractPage> {
    return request<ContractPage>(`/contracts${query({ ...params })}`);
  },

  get(id: string): Promise<ContractDetail> {
    return request<ContractDetail>(`/contracts/${id}`);
  },

  /**
   * Upload via XHR rather than fetch: extraction on a fifty-page file takes
   * a few seconds, and only XHR reports real upload progress. A frozen
   * screen reads as broken.
   */
  upload(
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<ContractDetail> {
    return new Promise((resolve, reject) => {
      const body = new FormData();
      body.append("file", file);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/contracts`);
      xhr.responseType = "text";

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };

      xhr.onload = () => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(xhr.responseText);
        } catch {
          parsed = undefined;
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(parsed as ContractDetail);
          return;
        }
        const detail = (parsed as { detail?: unknown })?.detail ?? parsed;
        reject(
          new ApiError(
            xhr.status,
            messageFromDetail(detail, `The server returned ${xhr.status}.`),
            detail,
          ),
        );
      };

      xhr.onerror = () =>
        reject(
          new ApiError(
            0,
            "Could not reach the backend. Is it running on 127.0.0.1:8000?",
          ),
        );

      xhr.send(body);
    });
  },

  supersede(id: string, file: File): Promise<ContractDetail> {
    const body = new FormData();
    body.append("file", file);
    return request<ContractDetail>(`/contracts/${id}/supersede`, {
      method: "POST",
      body,
    });
  },

  driverNote(id: string): Promise<string> {
    return request<string>(`/contracts/${id}/driver-note`);
  },

  previewUrl(id: string, page: number, boxes = false): string {
    return `${API_BASE}/contracts/${id}/preview/${page}${query({
      boxes: boxes ? "true" : undefined,
    })}`;
  },

  downloadUrl(id: string): string {
    return `${API_BASE}/contracts/${id}/download`;
  },

  approve(id: string, body: ApproveBody): Promise<ContractDetail> {
    return request<ContractDetail>(`/contracts/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  execute(id: string): Promise<ContractDetail> {
    return request<ContractDetail>(`/contracts/${id}/execute`, {
      method: "POST",
    });
  },

  resolveFlag(id: string, flagId: string, resolved: boolean): Promise<ContractDetail> {
    return request<ContractDetail>(`/contracts/${id}/flags/${flagId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolved }),
    });
  },

  void(id: string): Promise<ContractDetail> {
    return request<ContractDetail>(`/contracts/${id}/void`, { method: "POST" });
  },

  remove(id: string): Promise<void> {
    return request<void>(`/contracts/${id}`, { method: "DELETE" });
  },
};

/* --- Configuration --- */

export const configApi = {
  getFields(): Promise<FieldMap> {
    return request<FieldMap>("/config/fields");
  },

  putFields(map: FieldMap): Promise<FieldMap> {
    return request<FieldMap>("/config/fields", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(map),
    });
  },

  resetFields(): Promise<FieldMap> {
    return request<FieldMap>("/config/fields/reset", { method: "POST" });
  },

  getCarrier(): Promise<CarrierConfig> {
    return request<CarrierConfig>("/config/carrier");
  },

  putCarrier(carrier: CarrierConfig): Promise<CarrierConfig> {
    return request<CarrierConfig>("/config/carrier", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(carrier),
    });
  },

  uploadSignature(file: File): Promise<CarrierConfig> {
    const body = new FormData();
    body.append("file", file);
    return request<CarrierConfig>("/config/signature", { method: "POST", body });
  },

  signatureUrl(): string {
    return `${API_BASE}/config/signature`;
  },

  probe(file: File): Promise<ProbeResult> {
    const body = new FormData();
    body.append("file", file);
    return request<ProbeResult>("/config/probe", { method: "POST", body });
  },

  /**
   * Returns an object URL for the preview PNG plus which pages matched.
   * Revoke the URL when the caller is finished with it.
   */
  async testPlacement(
    contractId: string,
    signature: SignatureConfig,
    page?: number,
  ): Promise<{ url: string; page: number; pages: number[] }> {
    const response = await fetch(`${API_BASE}/config/test-placement`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract_id: contractId, signature, page }),
    });
    if (!response.ok) throw await toApiError(response);

    const blob = await response.blob();
    const pages = (response.headers.get("X-Placement-Pages") ?? "")
      .split(",")
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0);

    return {
      url: URL.createObjectURL(blob),
      page: Number(response.headers.get("X-Preview-Page") ?? page ?? 1),
      pages,
    };
  },
};

/* --- Audit --- */

export const auditApi = {
  list(page = 1, pageSize = 50): Promise<AuditPage> {
    return request<AuditPage>(`/audit${query({ page, page_size: pageSize })}`);
  },

  exportUrl(): string {
    return `${API_BASE}/audit/export`;
  },
};

export const healthApi = {
  check(): Promise<{ status: string }> {
    return request<{ status: string }>("/health");
  },
};
