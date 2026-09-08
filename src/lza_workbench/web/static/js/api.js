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
    throw new Error(body?.error?.message ?? "Unable to load configuration status.");
  }
  return body;
}
