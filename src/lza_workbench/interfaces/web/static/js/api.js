const apiCache = new Map();

export function clearApiCache() {
  apiCache.clear();
}

export function hasCachedData(key, ttl = 30000) {
  const cached = apiCache.get(key);
  return Boolean(cached && Date.now() - cached.timestamp < ttl);
}

export function getCachedData(key, ttl = 30000) {
  const cached = apiCache.get(key);
  if (cached && Date.now() - cached.timestamp < ttl) {
    return cached.data;
  }
  return null;
}

export async function getStatus({ refresh = false } = {}) {
  const cacheKey = "status";
  if (!refresh) {
    const cached = getCachedData(cacheKey, 30000);
    if (cached) return cached;
  }
  const url = `/api/status${refresh ? "?refresh=true" : ""}`;
  const response = await fetch(url);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(body?.error?.message ?? "Unable to load workspace status.");
    error.code = body?.error?.code;
    error.status = response.status;
    throw error;
  }
  apiCache.set(cacheKey, { timestamp: Date.now(), data: body });
  return body;
}

export async function getConfigurationStatus({ refresh = false } = {}) {
  const cacheKey = "config_status";
  if (!refresh) {
    const cached = getCachedData(cacheKey, 30000);
    if (cached) return cached;
  }
  const url = `/api/status/config${refresh ? "?refresh=true" : ""}`;
  const response = await fetch(url);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(body?.error?.message ?? body?.detail ?? "Unable to load configuration status.");
    error.code = body?.error?.code;
    error.status = response.status;
    throw error;
  }
  apiCache.set(cacheKey, { timestamp: Date.now(), data: body });
  return body;
}

export async function getInstallerStatus({ refresh = false } = {}) {
  const cacheKey = "installer_status";
  if (!refresh) {
    const cached = getCachedData(cacheKey, 30000);
    if (cached) return cached;
  }
  const url = `/api/status/installer${refresh ? "?refresh=true" : ""}`;
  const response = await fetch(url);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(body?.error?.message ?? body?.detail ?? "Unable to load installer status.");
    error.code = body?.error?.code;
    error.status = response.status;
    throw error;
  }
  apiCache.set(cacheKey, { timestamp: Date.now(), data: body });
  return body;
}

export async function saveInstallerSettings(values) {
  const response = await fetch("/api/installer/settings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ values }),
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    let message = body?.error?.message;
    if (!message && body?.detail) {
      message = Array.isArray(body.detail)
        ? body.detail.map((d) => d.msg || d.message).join("; ")
        : String(body.detail);
    }
    throw new Error(message ?? "Failed to save installer settings.");
  }
  clearApiCache();
  return body;
}

export async function getInstallerPlan() {
  const response = await fetch("/api/installer/plan", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Unable to generate installer deployment plan.");
  }
  return body;
}

export async function resetInstallerSettings() {
  const response = await fetch("/api/installer/reset", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to reset installer settings.");
  }
  clearApiCache();
  return body;
}

export async function prepareConfigPull() {
  const response = await fetch("/api/config/pull/prepare", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Unable to prepare configuration pull.");
  }
  return body;
}

export async function applyConfigPull({ overwriteConfirmed = false, force = false } = {}) {
  const response = await fetch("/api/config/pull/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      overwrite_confirmed: overwriteConfirmed,
      force,
    }),
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to pull configuration.");
  }
  clearApiCache();
  return body;
}

export async function prepareConfigPush() {
  const response = await fetch("/api/config/push/prepare", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Unable to prepare configuration push.");
  }
  return body;
}

export async function applyConfigPush({ overwriteConfirmed = false, force = false } = {}) {
  const response = await fetch("/api/config/push/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      overwrite_confirmed: overwriteConfirmed,
      force,
    }),
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to push configuration.");
  }
  clearApiCache();
  return body;
}

export async function getPipelineSnapshot({ type = "configuration", executionId = null, refresh = false } = {}) {
  const cacheKey = `pipeline_snapshot:${type}:${executionId || ""}`;
  if (!refresh) {
    const cached = getCachedData(cacheKey, 10000);
    if (cached) return cached;
  }
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (executionId) params.set("execution_id", executionId);
  if (refresh) params.set("refresh", "true");

  const response = await fetch(`/api/pipeline/snapshot?${params.toString()}`);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to load pipeline snapshot.");
  }
  apiCache.set(cacheKey, { timestamp: Date.now(), data: body });
  return body;
}

export async function getPipelineDiagnostics({ type = "configuration", executionId = null, refresh = false } = {}) {
  const cacheKey = `pipeline_diagnostics:${type}:${executionId || ""}`;
  if (!refresh) {
    const cached = getCachedData(cacheKey, 15000);
    if (cached) return cached;
  }
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (executionId) params.set("execution_id", executionId);
  if (refresh) params.set("refresh", "true");

  const response = await fetch(`/api/pipeline/diagnostics?${params.toString()}`);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to load pipeline diagnostics.");
  }
  apiCache.set(cacheKey, { timestamp: Date.now(), data: body });
  return body;
}

export async function applyConfigDeploy({ overwriteConfirmed = false, force = false } = {}) {
  const response = await fetch("/api/config/deploy", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      overwrite_confirmed: overwriteConfirmed,
      force,
    }),
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to deploy configuration.");
  }
  clearApiCache();
  return body;
}

export async function getActiveWorkspace() {
  const response = await fetch("/api/workspace/active");
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? "Failed to check active workspace.");
  }
  return body;
}

export async function openWorkspace(directory) {
  const response = await fetch("/api/workspace/open", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ directory }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to open workspace.");
  }
  clearApiCache();
  return body;
}

export async function previewWorkspaceInit(payload) {
  const response = await fetch("/api/workspace/init/preview", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to validate workspace initialization.");
  }
  return body;
}

export async function applyWorkspaceInit(payload) {
  const response = await fetch("/api/workspace/init/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to create workspace.");
  }
  clearApiCache();
  return body;
}

export async function discoverWorkspaceImport(payload) {
  const response = await fetch("/api/workspace/import/discover", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to discover workspace import.");
  }
  return body;
}

export async function prepareWorkspaceImport(payload) {
  const response = await fetch("/api/workspace/import/prepare", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to prepare workspace import.");
  }
  return body;
}

export async function applyWorkspaceImport() {
  const response = await fetch("/api/workspace/import/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to apply workspace import.");
  }
  clearApiCache();
  return body;
}

export async function getUninstallPlan(payload = {}) {
  const response = await fetch("/api/uninstall/plan", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to generate uninstallation plan.");
  }
  return body;
}

export async function applyUninstall(payload) {
  const response = await fetch("/api/uninstall/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to initiate uninstallation.");
  }
  clearApiCache();
  return body;
}

export async function getUninstallProgress() {
  const response = await fetch("/api/uninstall/progress");
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to fetch uninstallation progress.");
  }
  return body;
}

export async function resetUninstallProgress() {
  const response = await fetch("/api/uninstall/reset", {
    method: "POST",
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to reset uninstallation progress.");
  }
  clearApiCache();
  return body;
}



