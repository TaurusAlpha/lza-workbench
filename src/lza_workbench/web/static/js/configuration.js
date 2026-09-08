import { card, escapeHtml, formatFieldValue, renderBadge } from "./overview.js";

function formatTimestamp(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return String(isoStr);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return String(isoStr);
  }
}

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  const num = Number(bytes);
  if (isNaN(num)) return "—";
  if (num < 1024) return `${num} B`;
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} KB`;
  return `${(num / (1024 * 1024)).toFixed(2)} MB`;
}

function renderDiagnostics(warnings) {
  if (!warnings || warnings.length === 0) {
    return `
      <section class="diagnostic-panel diagnostic-panel-clean">
        <div class="diagnostic-status">
          <span class="badge badge-success"><span class="badge-dot" aria-hidden="true"></span>Clean</span>
          <span class="diagnostic-clean-text">No configuration warnings or diagnostic issues detected.</span>
        </div>
      </section>
    `;
  }

  const items = warnings
    .map(
      (warning) => `
      <li class="diagnostic-item">
        <svg class="diagnostic-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <span class="diagnostic-text">${escapeHtml(warning)}</span>
      </li>
    `
    )
    .join("");

  return `
    <section class="diagnostic-panel diagnostic-panel-warning">
      <div class="diagnostic-header">
        <span class="badge badge-warning"><span class="badge-dot" aria-hidden="true"></span>Attention</span>
        <h2 class="diagnostic-title">Diagnostics &amp; Recommendations (${warnings.length})</h2>
      </div>
      <ul class="diagnostic-list">${items}</ul>
    </section>
  `;
}


export function renderConfigurationDetails(container, status) {
  const ws = status.workspace;
  const git = status.localGit;
  const repo = status.repository;
  const sync = status.remoteSync;
  const syncHistory = status.synchronization;

  // 1. Local Configuration Fields
  const localDirStatus = ws.configDirExists ? "Present" : "Missing";
  const originStr = ws.initializedAt
    ? `Initialized from '${ws.templateName || "default"}' template (${formatTimestamp(ws.initializedAt)})`
    : ws.configDirExists
    ? "Imported / Unmanaged"
    : "Not initialized";

  const driftValue = ws.driftedFields && ws.driftedFields.length > 0
    ? ws.driftedFields.join(", ")
    : "None";

  const localConfigFields = [
    ["Directory", ws.configDir, { mono: true, truncate: true }],
    ["Directory state", localDirStatus, { statusIndicator: true }],
    ["Origin", originStr],
    ["Template source", ws.templateSource || "—", { mono: true }],
    ["Drifted fields", driftValue, { statusIndicator: driftValue !== "None" }],
    ["Discovered files", `${ws.yamlFilesCount} configuration file${ws.yamlFilesCount === 1 ? "" : "s"}`],
  ];

  // 2. Repository & Provider Fields
  const repoFields = [["Repository type", repo.type ? repo.type.toUpperCase() : "—", { mono: true }]];

  if (repo.type === "s3") {
    let bucketStatus = "Not Checked";
    if (repo.bucketExists === true) {
      bucketStatus = "Available";
    } else if (repo.bucketExists === false) {
      bucketStatus = "Not Found";
    } else if (repo.bucketAccessible === false) {
      bucketStatus = "Inaccessible";
    }

    const versioningStr = repo.bucketVersioning ? "Enabled" : "Disabled";
    const encryptionStr = repo.bucketEncryption ? "Enabled" : "Disabled";
    const objectStatus = repo.objectExists === true ? "Present" : repo.objectExists === false ? "Not uploaded yet" : "Not Checked";

    repoFields.push(
      ["S3 Bucket", repo.bucket, { mono: true, truncate: true }],
      ["Bucket status", bucketStatus, { statusIndicator: true }],
      ["Bucket versioning", versioningStr],
      ["Bucket encryption", encryptionStr],
      ["Object key", repo.objectKey, { mono: true }],
      ["Archive status", objectStatus, { statusIndicator: true }],
      ["Archive size", formatBytes(repo.objectSize)],
      ["Last modified", formatTimestamp(repo.objectLastModified)],
      ["ETag", repo.objectEtag, { mono: true, truncate: true }],
      ["Version ID", repo.objectVersionId, { mono: true, truncate: true }],
    );
    if (repo.error) {
      repoFields.push(["Provider error", repo.error]);
    }
  } else if (repo.type === "codecommit") {
    let repoStatus = "Not Checked";
    if (repo.exists === true) {
      repoStatus = "Available";
    } else if (repo.exists === false) {
      repoStatus = "Not Found";
    } else if (repo.accessible === false) {
      repoStatus = "Inaccessible";
    }

    let branchStatus = "Not Checked";
    if (repo.branchExists === true) {
      branchStatus = "Exists";
    } else if (repo.branchExists === false) {
      branchStatus = "Branch Not Found";
    }

    repoFields.push(
      ["Repository name", repo.repositoryName, { mono: true }],
      ["Repository status", repoStatus, { statusIndicator: true }],
      ["Branch", repo.branchName, { mono: true }],
      ["Branch status", branchStatus, { statusIndicator: true }],
    );
    if (repo.error) {
      repoFields.push(["Provider error", repo.error]);
    }
  } else if (repo.type === "codeconnection") {
    repoFields.push(
      ["Connection ARN", repo.connectionArn, { mono: true, truncate: true }],
      ["Connection status", repo.status, { statusIndicator: Boolean(repo.status) }],
      ["Provider type", repo.provider || "—"],
      ["Repository owner", repo.ownerAccount || repo.owner || "—", { mono: true }],
      ["Repository name", repo.repositoryName, { mono: true }],
      ["Branch", repo.branchName, { mono: true }],
    );
    if (repo.error) {
      repoFields.push(["Provider error", repo.error]);
    }
  } else if (repo.type === "git") {
    repoFields.push(
      ["Repository URL", repo.repositoryUrl || repo.repositoryName, { mono: true, truncate: true }],
      ["Branch", repo.branchName, { mono: true }],
    );
  }

  // 3. Git Working Tree Fields
  const wt = git.workingTree;
  let gitFields = [];
  if (!git.isGit || !wt) {
    gitFields = [
      ["Git state", "Not a Git repository or uninitialized", { statusIndicator: true }],
    ];
  } else {
    const workingTreeStatus = wt.hasUncommitted
      ? `Dirty (${wt.uncommittedCount} uncommitted change${wt.uncommittedCount === 1 ? "" : "s"})`
      : "Clean";

    gitFields = [
      ["Branch", wt.branch, { mono: true }],
      ["HEAD Commit", wt.commit, { mono: true }],
      ["Commit subject", wt.commitSubject || "—"],
      ["Working tree", workingTreeStatus, { statusIndicator: true }],
      ["Tracked files", wt.filesCount !== null && wt.filesCount !== undefined ? `${wt.filesCount} files` : "—"],
      ["Remote URL", wt.remoteUrl || "—", { mono: true, truncate: true }],
    ];
  }

  // 4. Remote Sync Fields
  let syncFields = [];
  if (!sync) {
    syncFields = [
      ["Sync status", "Sync unavailable or not checked", { statusIndicator: true }],
    ];
  } else {
    const isSyncedStr = sync.isSynced === true ? "Synchronized" : sync.isSynced === false ? "Out of sync" : sync.status;
    syncFields = [
      ["Sync status", isSyncedStr, { statusIndicator: true }],
      ["Summary", sync.summary],
      ["Ahead", `${sync.ahead} commit${sync.ahead === 1 ? "" : "s"}`],
      ["Behind", `${sync.behind} commit${sync.behind === 1 ? "" : "s"}`],
    ];
    const details = sync.details || {};
    if (details.local_digest) {
      syncFields.push(["Local digest", details.local_digest, { mono: true, truncate: true }]);
    }
    if (details.remote_digest) {
      syncFields.push(["Remote digest", details.remote_digest, { mono: true, truncate: true }]);
    }
    if (details.remote_etag) {
      syncFields.push(["Remote ETag", details.remote_etag, { mono: true, truncate: true }]);
    }
    if (details.error) {
      syncFields.push(["Sync error", details.error]);
    }
  }

  // 5. Synchronization History Fields
  const historyFields = [
    ["Workspace state recorded", syncHistory.hasState ? "Yes" : "No"],
    ["Last upload (Push)", formatTimestamp(syncHistory.uploadedAt)],
    ["Last download (Pull)", formatTimestamp(syncHistory.downloadedAt)],
    ["Recorded execution ID", syncHistory.recordedPipelineExecutionId || "—", { mono: true, truncate: true }],
    ["Recorded artifact ETag", syncHistory.artifactEtag || "—", { mono: true, truncate: true }],
  ];

  // 6. Configuration Pipeline Fields
  const pipe = status.pipeline;
  const pipeFields = [
    ["Pipeline name", pipe.name, { mono: true, truncate: true }],
    ["Pipeline ARN", pipe.arn, { mono: true, truncate: true }],
    ["Status", pipe.status || "Not Executed", { statusIndicator: Boolean(pipe.status) }],
    ["Latest execution ID", pipe.executionId || "—", { mono: true, truncate: true }],
  ];

  if (pipe.failedStage) {
    pipeFields.push(["Failed stage", pipe.failedStage, { mono: true }]);
  }
  if (pipe.failedAction) {
    pipeFields.push(["Failed action", pipe.failedAction, { mono: true }]);
  }
  if (pipe.error) {
    pipeFields.push(["Failure details", pipe.error]);
  }
  if (pipe.failedBuildUrl) {
    pipeFields.push(["Build console", pipe.failedBuildUrl, { mono: true, truncate: true }]);
  }

  container.innerHTML = `
    <div class="config-details-layout">
      ${renderDiagnostics(status.warnings)}

      <div class="details-grid">
        ${card("Local Configuration", localConfigFields, localDirStatus)}
        ${card("Repository & Provider", repoFields, repo.type ? repo.type.toUpperCase() : undefined)}
        ${card("Git State", gitFields, wt ? (wt.hasUncommitted ? "Dirty" : "Clean") : "Not Git")}
        ${card("Remote Sync State", syncFields, sync ? sync.status : "Unavailable")}
        ${card("Synchronization History", historyFields, syncHistory.hasState ? "Recorded" : "None")}
        ${card("Configuration Pipeline", pipeFields, pipe.status || "Not Executed", { href: "#/configuration-pipeline" })}
      </div>
    </div>
  `;

  container.querySelectorAll(".card-interactive").forEach((interactiveCard) => {
    interactiveCard.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) return;
      const href = interactiveCard.dataset.href;
      if (href) {
        window.location.hash = href;
      }
    });
  });
}
