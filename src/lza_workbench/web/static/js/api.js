export async function getStatus() {
  const response = await fetch("/api/status");
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? "Unable to load workspace status.");
  }
  return body;
}

export async function getConfigurationStatus() {
  const response = await fetch("/api/status/config");
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Unable to load configuration status.");
  }
  return body;
}

export async function getInstallerStatus() {
  const response = await fetch("/api/status/installer");
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Unable to load installer status.");
  }
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
  return body;
}

export async function getPipelineSnapshot({ type = "configuration", executionId = null } = {}) {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (executionId) params.set("execution_id", executionId);

  const response = await fetch(`/api/pipeline/snapshot?${params.toString()}`);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to load pipeline snapshot.");
  }
  return body;
}

export async function getPipelineDiagnostics({ type = "configuration", executionId = null } = {}) {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (executionId) params.set("execution_id", executionId);

  const response = await fetch(`/api/pipeline/diagnostics?${params.toString()}`);
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to load pipeline diagnostics.");
  }
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
  return body;
}

export async function getBootstrapPlan() {
  const response = await fetch("/api/bootstrap/plan");
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to load bootstrap plan.");
  }
  return body;
}

export async function applyBootstrap({ githubToken = null, allowMissingGithubSecret = false } = {}) {
  const response = await fetch("/api/bootstrap/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      github_token: githubToken,
      allow_missing_github_secret: allowMissingGithubSecret,
    }),
  });
  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(body?.error?.message ?? body?.detail ?? "Failed to apply bootstrap.");
  }
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
  return body;
}


