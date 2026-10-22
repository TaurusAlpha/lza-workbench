export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (character) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
  });
}

export function getStatusVariant(status) {
  if (!status) return "neutral";
  const norm = String(status).toLowerCase();

  // 1. Danger states (failures, errors, rollback, inaccessible)
  if (
    norm.includes("failed") ||
    norm.includes("cancelled") ||
    norm.includes("stopped") ||
    norm.includes("missing") ||
    norm.includes("inaccessible") ||
    norm.includes("diverged") ||
    norm.includes("out of sync") ||
    norm.includes("mismatch") ||
    norm.includes("error") ||
    norm === "offline" ||
    norm.includes("rollback")
  ) {
    return "danger";
  }

  // 2. Specific Warning states (active attention, drift, in-progress, local changes, live offline)
  if (
    norm.includes("attention") ||
    norm.includes("incomplete") ||
    norm.includes("running") ||
    norm.includes("in progress") ||
    norm.includes("inprogress") ||
    norm.includes("building") ||
    norm.includes("pending") ||
    norm.includes("ahead") ||
    norm.includes("behind") ||
    norm.includes("dirty") ||
    norm.includes("drift") ||
    norm.includes("local changes") ||
    norm.includes("aws unavailable") ||
    norm.includes("action required")
  ) {
    return "warning";
  }

  if (norm.includes("unavailable") || norm.includes("unknown") || norm === "—") {
    return "neutral";
  }
  if (norm.includes("not deployed") || norm.includes("not uploaded") || norm.includes("no upstream") || norm.includes("not started")) {
    return "warning";
  }

  // 3. Recorded/cached states: distinguish healthy recorded vs warning
  if (norm.startsWith("recorded:") || norm.startsWith("last known:")) {
    const stripped = norm.replace(/^(recorded|last known):\s*/, "");
    if (
      stripped.includes("complete") ||
      stripped.includes("in sync") ||
      stripped.includes("clean") ||
      stripped.includes("succeeded") ||
      stripped.includes("healthy") ||
      stripped.includes("available") ||
      stripped.includes("present") ||
      stripped.includes("exists") ||
      stripped.includes("live") ||
      stripped === "0"
    ) {
      return "recorded";
    }
    return "warning";
  }

  // 4. Success states (live positive outcomes)
  if (
    norm.includes("healthy") ||
    norm.includes("succeeded") ||
    norm.includes("complete") ||
    norm.includes("available") ||
    norm.includes("clean") ||
    norm.includes("in sync") ||
    norm.includes("synchronized") ||
    norm.includes("present") ||
    norm.includes("exists") ||
    norm.includes("live") ||
    norm === "0"
  ) {
    return "success";
  }

  return "neutral";
}

export function renderBadge(status) {
  if (status === null || status === undefined || status === "") return "";
  const variant = getStatusVariant(status);
  const text = escapeHtml(status);
  return `<span class="badge badge-${variant}" title="${text}"><span class="badge-dot" aria-hidden="true"></span>${text}</span>`;
}

function isInactiveOrEmpty(val) {
  if (val === null || val === undefined || val === "") return true;
  const str = String(val).trim().toLowerCase();
  return (
    str === "not available" ||
    str === "none" ||
    str === "not implemented yet" ||
    str === "none recorded" ||
    str === "—"
  );
}

export function formatFieldValue(fieldValue, options = {}) {
  if (options.raw) {
    return String(fieldValue);
  }

  if (isInactiveOrEmpty(fieldValue)) {
    const raw = fieldValue === null || fieldValue === undefined || fieldValue === "" ? "—" : String(fieldValue);
    const str = raw.trim().toLowerCase();
    const display = str === "not available" || str === "none" || str === "none recorded" || raw === "—" ? "—" : escapeHtml(raw);
    const tooltip = escapeHtml(raw);
    return `<span class="val-empty" title="${tooltip}">${display}</span>`;
  }

  if (options.statusIndicator) {
    const variant = getStatusVariant(fieldValue);
    const escaped = escapeHtml(fieldValue);
    return `<span class="status-indicator status-${variant}"><span class="status-dot" aria-hidden="true"></span><span class="status-val">${escaped}</span></span>`;
  }

  const rawStr = String(fieldValue);
  const escaped = escapeHtml(rawStr);

  const copyBtn = options.copy
    ? `<button type="button" class="btn-copy-inline" data-copy="${escaped}" title="${escapeHtml(options.copyLabel || "Copy value")}" aria-label="${escapeHtml(options.copyLabel || "Copy value")}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg>
      </button>`
    : "";

  if (options.mono) {
    if (options.truncate) {
      return `<span class="mono-val truncate" title="${escaped}">${escaped}</span>${copyBtn}`;
    }
    return `<span class="mono-val">${escaped}</span>${copyBtn}`;
  }

  if (options.truncate) {
    return `<span class="truncate" title="${escaped}">${escaped}</span>${copyBtn}`;
  }

  return `<span>${escaped}</span>${copyBtn}`;
}

export function card(title, fields, status, options = {}) {
  const rows = fields
    .filter(([, fieldValue]) => fieldValue !== undefined)
    .map(([label, fieldValue, fieldOptions = {}]) => {
      return `<div class="kv-row"><dt class="kv-label">${escapeHtml(label)}</dt><dd class="kv-value">${formatFieldValue(fieldValue, fieldOptions)}</dd></div>`;
    })
    .join("");
  const badge = status ? renderBadge(status) : "";
  const titleHtml = options.href
    ? `<h2 class="card-title"><a href="${options.href}" class="card-title-link" title="View ${escapeHtml(title)} details">${escapeHtml(title)}</a></h2>`
    : `<h2 class="card-title">${escapeHtml(title)}</h2>`;
  const interactiveClass = options.href ? " card-interactive" : "";
  const dataHref = options.href ? ` data-href="${escapeHtml(options.href)}"` : "";
  return `<article class="card${interactiveClass}"${dataHref}><div class="card-header">${titleHtml}${badge}</div><dl class="card-body">${rows}</dl></article>`;
}

function renderTimestamp(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return '<span class="val-empty">Time unavailable</span>';
  return `<time datetime="${escapeHtml(date.toISOString())}">${escapeHtml(date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }))}</time>`;
}

function renderLatestRun(pipeline) {
  if (!pipeline?.status || pipeline.status === "—") {
    return '<span class="val-empty">No run recorded</span>';
  }
  const label = pipeline.isLive ? pipeline.status : `Recorded: ${pipeline.status}`;
  return `<div class="overview-latest-run">
    ${formatFieldValue(label, { statusIndicator: true })}
    ${pipeline.executionId ? `<span class="run-start-time">${pipeline.startTime ? `Started ${renderTimestamp(pipeline.startTime)}` : "Start time unavailable"}</span>` : ""}
  </div>`;
}

function configurationSyncStatus(configuration, isLive = true) {
  if (configuration.localGitClean === false) {
    return "Local changes";
  }

  const sync = configuration.remoteSync || configuration.gitSync;
  if (!sync) {
    return "Sync unavailable";
  }

  switch (sync.status) {
    case "Synchronized":
      return isLive ? "In sync" : "Recorded: In sync";
    case "Ahead":
    case "Behind":
    case "Diverged":
      return "Drift detected";
    case "Not Uploaded":
      return "Not deployed";
    case "No Upstream":
      return "No Upstream";
    case undefined:
      return "Sync unavailable";
    default:
      return sync.status;
  }
}

export function renderOverview(container, status) {
  const configuration = status.configuration;
  const installer = status.installer;
  const configIsLive = configuration.isLive && status.aws.isLive;
  const installerIsLive = installer.isLive && status.aws.isLive;
  const installerStatus = installer.status || "Unknown";
  const installerStatusDisplay = installerIsLive ? installerStatus : `Recorded: ${installerStatus}`;
  const installerHealth = status.health?.installer || "Unknown";
  const installerBadge = installerIsLive || installerHealth.startsWith("Recorded:")
    ? installerHealth : `Recorded: ${installerHealth}`;
  const configSync = configurationSyncStatus(configuration, configIsLive);
  const remoteSync = configuration.remoteSync || configuration.gitSync;
  const remoteSyncSummary = remoteSync?.summary || remoteSync?.status || "Sync unavailable";
  const remoteSyncDisplay = configIsLive || !remoteSync ? remoteSyncSummary : `Recorded: ${remoteSyncSummary}`;
  const configPipeline = status.configurationPipeline;
  const configPipelineVariant = getStatusVariant(configPipeline?.status);
  const configBadge = configPipeline?.isLive && ["danger", "warning"].includes(configPipelineVariant)
    ? configPipeline.status : configSync;
  const directory = status.workspace.directory || "";
  const profile = status.aws.profile || "—";
  const region = status.aws.region || "—";
  const repoTarget = [configuration.repositoryType, configuration.target].filter(Boolean).join(" / ");
  const uncommitted = configuration.localGitClean === true ? "0 (Clean)"
    : configuration.localGitClean === false ? `${configuration.localGitUncommitted} uncommitted` : "Unknown";

  function renderNextStepsCard() {
    const steps = [];
    if (status.assessment && !status.assessment.installerConfigured) {
      steps.push({
        title: "Configure Installer",
        description: "Installer settings (AWS accounts, regions, repository) are incomplete.",
        action: "#/installer",
        actionText: "Configure Installer",
      });
    }
    if (status.assessment && !status.assessment.configurationPresent) {
      steps.push({
        title: "Initialize Configuration",
        description: "Local LZA configuration files are missing or not initialized.",
        action: "#/configuration",
        actionText: "Go to Configuration",
      });
    }

    if (steps.length === 0) return "";

    const stepItems = steps
      .map(
        (s) => `
      <li class="next-step-item">
        <div class="next-step-info">
          <strong class="next-step-title">${escapeHtml(s.title)}</strong>
          <span class="next-step-desc">${escapeHtml(s.description)}</span>
        </div>
        <a href="${escapeHtml(s.action)}" class="btn btn-sm btn-primary">${escapeHtml(s.actionText)}</a>
      </li>`
      )
      .join("");

    return `
      <article class="card card-full card-next-steps">
        <div class="card-header">
          <h2 class="card-title">Pending Workspace Actions</h2>
          <span class="badge badge-warning">${steps.length} pending</span>
        </div>
        <div class="card-body">
          <ul class="next-steps-list">
            ${stepItems}
          </ul>
        </div>
      </article>
    `;
  }

  function summaryRow(label, value, options = {}) {
    return `<div class="kv-row"><dt class="kv-label">${escapeHtml(label)}</dt>
      <dd class="kv-value">${formatFieldValue(value, options)}</dd></div>`;
  }

  function renderComponentCard({ title, href, badge, rows, pipeline, pipelineType, error }) {
    return `<article class="card workload-card card-interactive" data-href="${href}">
      <div class="card-header">
        <h2 class="card-title"><a href="${href}" class="card-title-link">${title}</a></h2>
        ${renderBadge(badge)}
      </div>
      <dl class="card-body">
        ${rows}
        <div class="kv-row"><dt class="kv-label">Latest run</dt><dd class="kv-value">${renderLatestRun(pipeline)}</dd></div>
      </dl>
      ${error ? `<p class="workload-error-box error-box-msg">${escapeHtml(error)}</p>` : ""}
      ${pipeline?.failureSummary ? `<p class="workload-error-box error-box-msg">${escapeHtml(pipeline.failureSummary)}</p>` : ""}
      ${pipeline?.error && !pipeline?.failureSummary ? `<p class="workload-error-box error-box-msg">${escapeHtml(pipeline.error)}</p>` : ""}
      <div class="card-footer">
        <a href="${href}" class="btn btn-sm btn-outline">Manage ${title.toLowerCase()} &rarr;</a>
        <a href="#/pipeline/${pipelineType}" class="btn btn-sm btn-ghost">View pipeline &rarr;</a>
      </div>
    </article>`;
  }

  container.innerHTML = `
    <article class="card card-full workspace-context-bar">
      <div class="context-bar-header">
        <h2 class="context-bar-title">Workspace &amp; AWS context</h2>
        <div class="context-bar-badges">
          ${renderBadge(status.aws.isLive ? "Live" : "Offline")}
          <span class="badge badge-neutral">LZA version: ${escapeHtml(status.workspace.lzaVersion || "Unknown")}</span>
          <a href="#/welcome" class="btn btn-sm btn-outline">Switch workspace &rarr;</a>
        </div>
      </div>
      <div class="context-bar-details">
        <div class="context-item context-directory"><span class="context-label">Directory</span>
          <div class="context-val">${formatFieldValue(directory, { mono: true, copy: Boolean(directory), copyLabel: "Copy workspace directory" })}</div>
        </div>
        <div class="context-item"><span class="context-label">AWS profile</span>
          <div class="context-val">${formatFieldValue(profile, { mono: true, copy: Boolean(status.aws.profile), copyLabel: "Copy AWS profile" })}</div>
        </div>
        <div class="context-item"><span class="context-label">AWS region</span>
          <div class="context-val">${formatFieldValue(region, { mono: true, copy: Boolean(status.aws.region), copyLabel: "Copy AWS region" })}</div>
        </div>
      </div>
      <p class="overview-refreshed">Last refreshed: ${renderTimestamp(status.observedAt)}</p>
    </article>
    ${renderNextStepsCard()}
    <div class="workload-grid card-full">
      ${renderComponentCard({
        title: "Installer", href: "#/installer", badge: installerBadge,
        rows: summaryRow("Settings", status.assessment?.installerConfigured === true ? "Configured" : status.assessment?.installerConfigured === false ? "Incomplete" : "Unknown")
          + summaryRow("Deployed version", installer.deployedVersion, { mono: true })
          + summaryRow("Stack status", installerStatusDisplay, { statusIndicator: true }),
        pipeline: status.installerPipeline, pipelineType: "installer",
        error: installer.error,
      })}
      ${renderComponentCard({
        title: "Configuration", href: "#/configuration", badge: configBadge,
        rows: summaryRow("Repository", repoTarget, { mono: true, copy: Boolean(repoTarget), copyLabel: "Copy configuration repository" })
          + summaryRow("Local branch", configuration.localGitBranch, { mono: true })
          + summaryRow("Local changes", uncommitted)
          + summaryRow("Remote sync", remoteSyncDisplay, { statusIndicator: true }),
        pipeline: configPipeline, pipelineType: "configuration",
        error: configuration.error,
      })}
    </div>
    <details class="card card-full card-danger-zone" id="danger-zone-card">
      <summary class="danger-zone-summary"><h2 class="card-title">Danger Zone</h2><span class="danger-zone-desc">Decommission this LZA environment</span></summary>
      <div class="danger-zone-body">
        <div class="danger-action-row">
          <div class="danger-action-info">
            <strong class="danger-action-title">Uninstall Landing Zone Accelerator</strong>
            <p class="danger-action-desc">Review accelerator-managed resources for removal across target accounts. Deletion is irreversible.</p>
          </div>
          <a href="#/uninstall" class="btn btn-sm btn-outline-danger" id="btn-uninstall-overview">Uninstall solution…</a>
        </div>
      </div>
    </details>`;

  container.querySelectorAll(".card-interactive").forEach((interactiveCard) => {
    interactiveCard.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input") || window.getSelection()?.toString()) return;
      window.location.hash = interactiveCard.dataset.href;
    });
  });

  container.querySelectorAll(".btn-copy-inline").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        btn.classList.add("copied");
        setTimeout(() => btn.classList.remove("copied"), 1500);
      } catch (err) {
        console.warn("Clipboard copy failed:", err);
      }
    });
  });
}
