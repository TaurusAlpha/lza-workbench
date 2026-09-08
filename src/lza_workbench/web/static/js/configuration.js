import { applyConfigPull, applyConfigPush, prepareConfigPull, prepareConfigPush } from "./api.js";
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


export function renderConfigurationDetails(container, status, onRefresh) {
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
    repoFields.push(
      ["Repository name", repo.codeCommitRepositoryName || "—", { mono: true }],
      ["Branch", repo.codeCommitBranch || "—", { mono: true }],
      ["Region", repo.codeCommitRegion || "—", { mono: true }],
      ["Clone URL (HTTP)", repo.codeCommitCloneUrlHttp || "—", { mono: true, truncate: true }]
    );
  } else if (repo.type === "codeconnection") {
    repoFields.push(
      ["Repository name", repo.codeConnectionRepositoryName || "—", { mono: true }],
      ["Branch", repo.codeConnectionBranch || "—", { mono: true }],
      ["Owner", repo.codeConnectionOwner || "—", { mono: true }],
      ["Connection ARN", repo.codeConnectionArn || "—", { mono: true, truncate: true }]
    );
  } else if (repo.type === "git") {
    repoFields.push(
      ["Repository URL", repo.gitRepositoryUrl || "—", { mono: true, truncate: true }],
      ["Branch", repo.gitBranch || "—", { mono: true }]
    );
  }

  // 3. Git Working Tree State Fields
  const wt = git.workingTree;
  let gitFields = [];
  if (!git.isGitRepo) {
    gitFields = [
      ["Repository", "Not a Git repository", { statusIndicator: true }],
      ["Directory", ws.configDir, { mono: true, truncate: true }],
    ];
  } else {
    gitFields = [
      ["Branch", git.branch || "—", { mono: true }],
      ["Head commit", git.headCommit || "—", { mono: true }],
      ["Remote URL", git.remoteUrl || "—", { mono: true, truncate: true }],
      ["Status", wt ? (wt.hasUncommitted ? "Uncommitted changes" : "Clean") : "Unknown", { statusIndicator: true }],
      ["Tracked files", git.filesCount !== null ? String(git.filesCount) : "—"],
    ];
    if (wt && wt.hasUncommitted) {
      const parts = [];
      if (wt.untrackedFiles && wt.untrackedFiles.length) parts.push(`${wt.untrackedFiles.length} untracked`);
      if (wt.modifiedFiles && wt.modifiedFiles.length) parts.push(`${wt.modifiedFiles.length} modified`);
      if (wt.stagedFiles && wt.stagedFiles.length) parts.push(`${wt.stagedFiles.length} staged`);
      gitFields.push(["Uncommitted detail", parts.join(", ") || "Modified"]);
    }
  }

  // 4. Remote Synchronization State Fields
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
      <div class="config-actions-bar">
        <div class="config-actions-group">
          <button type="button" id="btn-config-pull" class="btn">
            <span>Pull Configuration</span>
          </button>
          <button type="button" id="btn-config-push" class="btn btn-primary">
            <span>Push Configuration</span>
          </button>
        </div>
      </div>

      ${renderDiagnostics(status.warnings)}

      <div class="details-grid">
        ${card("Local Configuration", localConfigFields, localDirStatus)}
        ${card("Repository & Provider", repoFields, repo.type ? repo.type.toUpperCase() : undefined)}
        ${card("Git State", gitFields, wt ? (wt.hasUncommitted ? "Dirty" : "Clean") : "Not Git")}
        ${card("Remote Sync State", syncFields, sync ? sync.status : "Unavailable")}
        ${card("Synchronization History", historyFields, syncHistory.hasState ? "Recorded" : "None")}
        ${card("Configuration Pipeline", pipeFields, pipe.status || "Not Executed", { href: "#/configuration-pipeline" })}
      </div>

      <div id="config-action-modal-container" hidden></div>
    </div>
  `;

  // Attach interactive card clicks
  container.querySelectorAll(".card-interactive").forEach((interactiveCard) => {
    interactiveCard.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) return;
      const href = interactiveCard.dataset.href;
      if (href) {
        window.location.hash = href;
      }
    });
  });

  // Attach Pull and Push action handlers
  container.querySelector("#btn-config-pull")?.addEventListener("click", () => {
    openConfigActionModal(container, "pull", onRefresh);
  });
  container.querySelector("#btn-config-push")?.addEventListener("click", () => {
    openConfigActionModal(container, "push", onRefresh);
  });
}

async function openConfigActionModal(container, actionType, onRefresh) {
  const modalContainer = container.querySelector("#config-action-modal-container");
  if (!modalContainer) return;

  const actionTitle = actionType === "pull" ? "Pull Configuration" : "Push Configuration";
  const prepFn = actionType === "pull" ? prepareConfigPull : prepareConfigPush;
  const applyFn = actionType === "pull" ? applyConfigPull : applyConfigPush;

  modalContainer.hidden = false;
  modalContainer.innerHTML = `
    <div class="plan-modal-overlay">
      <div class="plan-modal-card" style="max-width: 36rem;">
        <div class="plan-modal-header">
          <h3 class="plan-modal-title">Preparing ${escapeHtml(actionTitle)}&hellip;</h3>
          <button type="button" class="btn btn-sm btn-close-modal" title="Cancel">✕</button>
        </div>
        <div class="plan-modal-body">
          <p class="plan-loading-text">Inspecting repository and assessing configuration changes&hellip;</p>
        </div>
      </div>
    </div>
  `;

  function closeModal() {
    modalContainer.hidden = true;
    modalContainer.innerHTML = "";
  }

  modalContainer.querySelector(".btn-close-modal").addEventListener("click", closeModal);

  let prep;
  try {
    prep = await prepFn();
  } catch (err) {
    modalContainer.innerHTML = `
      <div class="plan-modal-overlay">
        <div class="plan-modal-card" style="max-width: 36rem;">
          <div class="plan-modal-header">
            <h3 class="plan-modal-title">${escapeHtml(actionTitle)} Assessment Failed</h3>
            <button type="button" class="btn btn-sm btn-close-modal" title="Close">✕</button>
          </div>
          <div class="plan-modal-body">
            <div class="notice error">${escapeHtml(err.message)}</div>
          </div>
          <div class="plan-modal-footer">
            <button type="button" class="btn btn-close-modal">Close</button>
          </div>
        </div>
      </div>
    `;
    modalContainer.querySelectorAll(".btn-close-modal").forEach((b) => b.addEventListener("click", closeModal));
    return;
  }

  // Render preparation assessment
  const requiresConfirm = Boolean(prep.requiresConfirmation);
  const targetLabel = prep.repositoryType === "s3" ? "S3 Destination" : "Git Remote";
  const branchRow = prep.branch
    ? `<div class="plan-summary-item"><span class="plan-summary-label">Branch</span><span class="mono-val">${escapeHtml(prep.branch)}</span></div>`
    : "";
  const trackedFilesRow = prep.trackedFiles !== undefined && prep.trackedFiles !== null
    ? `<div class="plan-summary-item"><span class="plan-summary-label">Tracked Files</span><span>${escapeHtml(prep.trackedFiles)}</span></div>`
    : "";

  let riskNoticeHtml = "";
  let confirmCheckboxHtml = "";
  let executeBtnHtml = "";

  if (requiresConfirm) {
    riskNoticeHtml = `
      <div class="notice warning" style="margin-top: 1rem;">
        <strong>Warning:</strong> ${escapeHtml(prep.confirmationReason || "Operation requires confirmation.")}
      </div>
    `;
    confirmCheckboxHtml = `
      <div class="confirmation-checkbox-container">
        <input type="checkbox" id="chk-confirm-action" />
        <label for="chk-confirm-action">I understand the potential overwrite or conflict risks and want to proceed.</label>
      </div>
    `;
    executeBtnHtml = `
      <button type="button" id="btn-execute-action" class="btn btn-danger" disabled>
        <span>Confirm &amp; ${escapeHtml(actionType === "pull" ? "Pull" : "Push")}</span>
      </button>
    `;
  } else {
    riskNoticeHtml = `
      <div class="notice info" style="margin-top: 1rem;">
        No overwrite or conflict risks detected. This operation is ready to proceed.
      </div>
    `;
    executeBtnHtml = `
      <button type="button" id="btn-execute-action" class="btn btn-primary">
        <span>Execute ${escapeHtml(actionType === "pull" ? "Pull" : "Push")}</span>
      </button>
    `;
  }

  modalContainer.innerHTML = `
    <div class="plan-modal-overlay">
      <div class="plan-modal-card" style="max-width: 36rem;">
        <div class="plan-modal-header">
          <div>
            <h3 class="plan-modal-title">${escapeHtml(actionTitle)}</h3>
            <p class="section-subtitle">${escapeHtml(prep.operation)}</p>
          </div>
          <button type="button" class="btn btn-sm btn-close-modal" title="Cancel">✕</button>
        </div>
        <div class="plan-modal-body">
          <div class="plan-summary-grid">
            <div class="plan-summary-item">
              <span class="plan-summary-label">${escapeHtml(targetLabel)}</span>
              <span class="mono-val" style="word-break: break-all;">${escapeHtml(prep.target)}</span>
            </div>
            <div class="plan-summary-item">
              <span class="plan-summary-label">Repository Type</span>
              <span class="mono-val">${escapeHtml(prep.repositoryType.toUpperCase())}</span>
            </div>
            ${branchRow}
            ${trackedFilesRow}
          </div>

          ${riskNoticeHtml}
          ${confirmCheckboxHtml}

          <div id="action-modal-alert" aria-live="polite"></div>
        </div>
        <div class="plan-modal-footer" style="gap: 0.75rem;">
          <button type="button" class="btn btn-close-modal">Cancel</button>
          ${executeBtnHtml}
        </div>
      </div>
    </div>
  `;

  modalContainer.querySelectorAll(".btn-close-modal").forEach((b) => b.addEventListener("click", closeModal));

  const btnExecute = modalContainer.querySelector("#btn-execute-action");
  const chkConfirm = modalContainer.querySelector("#chk-confirm-action");
  const modalAlert = modalContainer.querySelector("#action-modal-alert");

  if (chkConfirm) {
    chkConfirm.addEventListener("change", () => {
      btnExecute.disabled = !chkConfirm.checked;
    });
  }

  btnExecute.addEventListener("click", async () => {
    btnExecute.disabled = true;
    btnExecute.innerHTML = `<span>Applying ${escapeHtml(actionType === "pull" ? "Pull" : "Push")}&hellip;</span>`;
    modalAlert.innerHTML = `
      <div class="notice info">
        Synchronizing configuration&hellip;
      </div>
    `;

    try {
      const applyResult = await applyFn({ overwriteConfirmed: true });
      let diffSummaryHtml = "";
      if (applyResult.diff && applyResult.diff.total > 0) {
        diffSummaryHtml = `
          <div style="margin-top: 0.75rem; font-size: 0.8125rem;">
            Changes: <strong>${applyResult.diff.added.length} added</strong>,
            <strong>${applyResult.diff.modified.length} modified</strong>,
            <strong>${applyResult.diff.removed.length} removed</strong>.
          </div>
        `;
      }

      modalContainer.innerHTML = `
        <div class="plan-modal-overlay">
          <div class="plan-modal-card" style="max-width: 36rem;">
            <div class="plan-modal-header">
              <h3 class="plan-modal-title">${escapeHtml(actionTitle)} Complete</h3>
              <button type="button" class="btn btn-sm btn-done" title="Close">✕</button>
            </div>
            <div class="plan-modal-body">
              <div class="notice success">
                ${escapeHtml(applyResult.message)}
              </div>
              ${diffSummaryHtml}
            </div>
            <div class="plan-modal-footer">
              <button type="button" class="btn btn-primary btn-done">Done</button>
            </div>
          </div>
        </div>
      `;

      modalContainer.querySelectorAll(".btn-done").forEach((b) => {
        b.addEventListener("click", () => {
          closeModal();
          if (typeof onRefresh === "function") {
            onRefresh();
          }
        });
      });
    } catch (err) {
      btnExecute.disabled = false;
      btnExecute.innerHTML = `<span>Retry ${escapeHtml(actionType === "pull" ? "Pull" : "Push")}</span>`;
      modalAlert.innerHTML = `
        <div class="notice error">
          ${escapeHtml(err.message)}
        </div>
      `;
    }
  });
}
