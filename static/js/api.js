/** Thin fetch wrapper around the MaintainIQ JSON API. */

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** FastAPI returns `{detail: "..."}` or `{detail: [{msg, loc}]}` for 422s. */
function detailMessage(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const [first] = detail;
    if (first && typeof first.msg === "string") return first.msg;
  }
  if (status === 404) return "That item no longer exists.";
  return `Request failed (HTTP ${status}).`;
}

async function request(path, { method = "GET", body, formData } = {}) {
  const options = { method, headers: {} };

  if (formData) {
    options.body = formData;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError("Cannot reach the MaintainIQ server. Is it still running?");
  }

  const contentType = response.headers.get("content-type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(detailMessage(payload, response.status), response.status);
  }

  return payload;
}

export const api = {
  status: () => request("/api/status"),

  dashboard: () => request("/api/dashboard"),

  equipment: () => request("/api/equipment"),
  addEquipment: (body) => request("/api/equipment", { method: "POST", body }),
  updateEquipment: (id, body) => request(`/api/equipment/${id}`, { method: "PATCH", body }),
  deleteEquipment: (id) => request(`/api/equipment/${id}`, { method: "DELETE" }),

  technicians: () => request("/api/technicians"),
  addTechnician: (body) => request("/api/technicians", { method: "POST", body }),
  updateTechnician: (id, body) => request(`/api/technicians/${id}`, { method: "PATCH", body }),
  deleteTechnician: (id) => request(`/api/technicians/${id}`, { method: "DELETE" }),

  previewTriage: (body) => request("/api/issues/triage", { method: "POST", body }),
  createIssue: (body) => request("/api/issues", { method: "POST", body }),
  issues: () => request("/api/issues"),
  updateIssue: (id, body) => request(`/api/issues/${id}`, { method: "PATCH", body }),
  closeIssue: (id, body) => request(`/api/issues/${id}/records`, { method: "POST", body }),

  records: () => request("/api/records"),
  addRecord: (body) => request("/api/records", { method: "POST", body }),

  documents: () => request("/api/knowledge/documents"),
  uploadDocuments: (formData) =>
    request("/api/knowledge/documents", { method: "POST", formData }),
  ask: (question) => request("/api/knowledge/ask", { method: "POST", body: { question } }),

  reports: () => request("/api/reports"),
};
