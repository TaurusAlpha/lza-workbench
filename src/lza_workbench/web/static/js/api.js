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
