import { applyBootstrap, getBootstrapPlan } from "./api.js";
import { card, escapeHtml, renderBadge } from "./overview.js";

function getOperationBadgeVariant(op) {
  if (!op) return "neutral";
  const norm = String(op).toUpperCase();
  if (norm === "NO_CHANGE" || norm === "CLEAN" || norm === "OK") return "success";
  if (norm === "CREATE") return "info";
  if (norm === "UPDATE" || norm === "WARNING" || norm === "OFFLINE") return "warning";
  if (norm === "MISSING" || norm === "INACCESSIBLE" || norm === "ERROR") return "danger";
  return "neutral";
}

function renderOperationBadge(op) {
  const variant = getOperationBadgeVariant(op);
  const label = op ? String(op).replace(/_/g, " ") : "Unknown";
  return `<span class="badge badge-${variant}"><span class="badge-dot" aria-hidden="true"></span>${escapeHtml(label)}</span>`;
}

function renderWarnings(warnings) {
  if (!warnings || warnings.length === 0) return "";
  const items = warnings
    .map(
      (w) => `
      <li class="diagnostic-item">
        <svg class="diagnostic-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <span class="diagnostic-text">${escapeHtml(w)}</span>
      </li>
    `
    )
    .join("");

  return `
    <section class="diagnostic-panel diagnostic-panel-warning" style="margin-bottom: 1.5rem;">
      <div class="diagnostic-header">
        <span class="badge badge-warning"><span class="badge-dot" aria-hidden="true"></span>Warning</span>
        <h2 class="diagnostic-title">Prerequisite Warnings (${warnings.length})</h2>
      </div>
      <ul class="diagnostic-list">${items}</ul>
    </section>
  `;
}

function renderActionsList(actions) {
  if (!actions || actions.length === 0) {
    return `
      <div class="field-row">
        <span class="field-value text-muted">No actions planned.</span>
      </div>
    `;
  }

  return actions
    .map((action) => {
      const variant = getOperationBadgeVariant(action.operation);
      return `
        <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 0.75rem 0; border-bottom: 1px solid var(--border-subtle, #f1f5f9);">
          <div style="flex: 1;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
              <strong style="font-size: 0.875rem; color: var(--text-primary);">${escapeHtml(action.subject)}</strong>
              <span class="badge badge-${variant}"><span class="badge-dot" aria-hidden="true"></span>${escapeHtml(action.operation)}</span>
            </div>
            <p style="font-size: 0.8125rem; color: var(--text-secondary, #64748b); margin: 0;">${escapeHtml(action.message)}</p>
          </div>
        </div>
      `;
    })
    .join("");
}

export function renderBootstrapDetails(container, plan, onRefresh) {
  const bucket = plan.resources.bucket;
  const cc = plan.resources.codecommit;
  const gh = plan.resources.github;

  // Imported workspace callout
  let importedBanner = "";
  if (plan.imported) {
    importedBanner = `
      <div class="notice info" style="margin-bottom: 1.5rem;">
        <strong>Imported Workspace:</strong> Pre-existing infrastructure is managed externally.
        Missing AWS resources are validated only and will not be created automatically.
      </div>
    `;
  }

  // S3 Bucket Card fields
  const bucketFields = [
    ["Bucket name", bucket.name, { mono: true, truncate: true }],
    ["Bucket exists", plan.isLive ? (bucket.exists ? "Yes" : "No") : "Unknown (Offline)", { statusIndicator: plan.isLive }],
    ["Versioning", plan.isLive ? (bucket.versioningEnabled ? "Enabled" : "Disabled") : "—"],
    ["KMS encryption", plan.isLive ? (bucket.encryptionEnabled ? "Enabled" : "Disabled") : "—"],
  ];

  // CodeCommit Card fields
  let ccCardHtml = "";
  if (cc) {
    const ccFields = [
      ["Repository", cc.name, { mono: true, truncate: true }],
      ["Target branch", cc.branch || "main", { mono: true }],
      ["Repository exists", plan.isLive ? (cc.exists ? "Yes" : "No") : "Unknown (Offline)", { statusIndicator: plan.isLive }],
      ["Branch exists", plan.isLive ? (cc.branchExists ? "Yes" : "No") : "—"],
    ];
    ccCardHtml = card("Configuration Repository", ccFields, cc.plannedOperation);
  }

  // GitHub Secret Card fields
  let ghCardHtml = "";
  if (gh) {
    const ghFields = [
      ["Secret name", gh.secretName || "—", { mono: true, truncate: true }],
      ["Secret exists", plan.isLive ? (gh.secretExists ? "Yes" : "No") : "Unknown (Offline)", { statusIndicator: plan.isLive }],
      ["Secret accessible", plan.isLive ? (gh.secretAccessible ? "Yes" : "No") : "—"],
      ["Target repo", `${gh.repoOwner || "—"}/${gh.repoName || "—"}:${gh.repoBranch || "—"}`, { mono: true }],
      ["Repo accessible", plan.isLive ? (gh.repoAccessible ? "Yes" : "No") : "—"],
    ];
    ghCardHtml = card("GitHub Secret", ghFields, gh.plannedOperation);
  }

  // Action status / Apply button state
  let applyControlsHtml = "";
  if (!plan.isLive) {
    applyControlsHtml = `
      <div class="notice warning" style="margin-top: 1rem;">
        <strong>AWS is offline:</strong> Authentication is required to plan and apply prerequisite resources.
      </div>
      <button type="button" class="btn btn-primary" style="margin-top: 0.75rem;" disabled title="AWS is offline">
        Apply Bootstrap
      </button>
    `;
  } else if (plan.isMutationRequired) {
    if (plan.imported && cc && cc.plannedOperation === "MISSING") {
      applyControlsHtml = `
        <div class="notice danger" style="margin-top: 1rem;">
          <strong>Blocked:</strong> Configured CodeCommit repository '${escapeHtml(cc.name)}' does not exist in AWS.
          Imported resources cannot be recreated automatically.
        </div>
        <button type="button" class="btn btn-primary" style="margin-top: 0.75rem;" disabled title="Blocked by missing imported repository">
          Apply Bootstrap
        </button>
      `;
    } else {
      applyControlsHtml = `
        <div style="margin-top: 1rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
          <div style="font-size: 0.8125rem; color: var(--text-secondary, #64748b);">
            Changes to prerequisite AWS resources are planned.
          </div>
          <button type="button" id="btn-open-bootstrap-apply" class="btn btn-primary">
            <span>Apply Bootstrap</span>
          </button>
        </div>
      `;
    }
  } else {
    applyControlsHtml = `
      <div class="notice success" style="margin-top: 1rem;">
        Prerequisites in sync. No AWS changes required.
      </div>
    `;
  }

  container.innerHTML = `
    <div style="margin-bottom: 1.5rem;">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; margin-bottom: 0.75rem;">
        <div>
          <h2 style="font-size: 1.125rem; font-weight: 600; margin: 0 0 0.25rem 0;">Prerequisite AWS Resources</h2>
          <p style="font-size: 0.8125rem; color: var(--text-secondary, #64748b); margin: 0;">
            Target: <code class="mono-val">${escapeHtml(plan.awsProfile)}</code> &bull;
            Region: <code class="mono-val">${escapeHtml(plan.awsRegion)}</code> &bull;
            Account: <code class="mono-val">${escapeHtml(plan.accountId)}</code>
          </p>
        </div>
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <span style="font-size: 0.8125rem; color: var(--text-muted);">Plan status:</span>
          ${renderOperationBadge(plan.plannedOperation)}
        </div>
      </div>
      ${importedBanner}
    </div>

    <div class="card-grid" style="margin-bottom: 1.5rem;">
      ${card("Workbench Assets Bucket", bucketFields, bucket.plannedOperation)}
      ${ccCardHtml}
      ${ghCardHtml}
    </div>

    ${renderWarnings(plan.warnings)}

    <section class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <h3 class="card-title">Planned Actions</h3>
        <span class="badge badge-neutral">${plan.actions ? plan.actions.length : 0} actions</span>
      </div>
      <div class="card-body">
        ${renderActionsList(plan.actions)}
        ${applyControlsHtml}
      </div>
    </section>

    <div id="bootstrap-modal-container"></div>
  `;

  const btnOpenApply = container.querySelector("#btn-open-bootstrap-apply");
  if (btnOpenApply) {
    btnOpenApply.addEventListener("click", () => {
      openBootstrapApplyModal(container, plan, onRefresh);
    });
  }
}

function openBootstrapApplyModal(container, plan, onRefresh) {
  const modalContainer = container.querySelector("#bootstrap-modal-container");
  if (!modalContainer) return;

  const closeModal = () => {
    modalContainer.replaceChildren();
  };

  const gh = plan.resources.github;
  const showGithubTokenInput = gh && (gh.plannedOperation === "MISSING" || gh.plannedOperation === "INACCESSIBLE");

  let githubTokenHtml = "";
  if (showGithubTokenInput) {
    githubTokenHtml = `
      <div style="margin-top: 1rem; padding: 0.75rem; background: var(--bg-card, #f8fafc); border: 1px solid var(--border-card); border-radius: 0.375rem;">
        <label for="input-github-token" style="display: block; font-size: 0.8125rem; font-weight: 500; margin-bottom: 0.25rem;">
          GitHub Personal Access Token (Optional):
        </label>
        <input type="password" id="input-github-token" class="input" placeholder="ghp_..." style="width: 100%; font-size: 0.8125rem; padding: 0.375rem 0.5rem; margin-bottom: 0.5rem; border: 1px solid var(--border-card); border-radius: 0.25rem;" />
        <div style="display: flex; align-items: center; gap: 0.5rem;">
          <input type="checkbox" id="chk-allow-missing-gh" />
          <label for="chk-allow-missing-gh" style="font-size: 0.75rem; color: var(--text-secondary, #64748b);">
            Allow missing GitHub secret (continue without storing token in Secrets Manager)
          </label>
        </div>
      </div>
    `;
  }

  modalContainer.innerHTML = `
    <div class="plan-modal-overlay">
      <div class="plan-modal-card" style="max-width: 36rem;">
        <div class="plan-modal-header">
          <div>
            <h3 class="plan-modal-title">Apply Bootstrap Changes</h3>
            <p class="section-subtitle">Provision prerequisite AWS resources</p>
          </div>
          <button type="button" class="btn btn-sm btn-close-modal" title="Cancel">✕</button>
        </div>
        <div class="plan-modal-body">
          <p style="font-size: 0.8125rem; color: var(--text-secondary, #64748b); margin: 0 0 1rem 0;">
            The following actions will be executed against AWS account
            <code class="mono-val">${escapeHtml(plan.accountId)}</code> in region
            <code class="mono-val">${escapeHtml(plan.awsRegion)}</code>:
          </p>

          <div style="max-height: 12rem; overflow-y: auto; margin-bottom: 1rem; padding: 0.5rem; background: var(--bg-card, #f8fafc); border: 1px solid var(--border-card); border-radius: 0.375rem;">
            ${renderActionsList(plan.actions)}
          </div>

          ${githubTokenHtml}

          <div class="confirmation-checkbox-container" style="margin-top: 1rem;">
            <input type="checkbox" id="chk-confirm-bootstrap" />
            <label for="chk-confirm-bootstrap">
              I understand that these changes will mutate prerequisite AWS infrastructure.
            </label>
          </div>

          <div id="bootstrap-modal-alert" aria-live="polite" style="margin-top: 0.75rem;"></div>
        </div>
        <div class="plan-modal-footer" style="gap: 0.75rem;">
          <button type="button" class="btn btn-close-modal">Cancel</button>
          <button type="button" id="btn-execute-bootstrap" class="btn btn-primary" disabled>
            <span>Confirm &amp; Apply</span>
          </button>
        </div>
      </div>
    </div>
  `;

  modalContainer.querySelectorAll(".btn-close-modal").forEach((b) => b.addEventListener("click", closeModal));

  const btnExecute = modalContainer.querySelector("#btn-execute-bootstrap");
  const chkConfirm = modalContainer.querySelector("#chk-confirm-bootstrap");
  const modalAlert = modalContainer.querySelector("#bootstrap-modal-alert");
  const inputGhToken = modalContainer.querySelector("#input-github-token");
  const chkAllowMissingGh = modalContainer.querySelector("#chk-allow-missing-gh");

  if (chkConfirm) {
    chkConfirm.addEventListener("change", () => {
      btnExecute.disabled = !chkConfirm.checked;
    });
  }

  btnExecute.addEventListener("click", async () => {
    btnExecute.disabled = true;
    btnExecute.innerHTML = `<span>Applying bootstrap&hellip;</span>`;
    modalAlert.innerHTML = `
      <div class="notice info">
        Provisioning prerequisite AWS resources. Please wait&hellip;
      </div>
    `;

    const githubToken = inputGhToken ? inputGhToken.value.trim() || null : null;
    const allowMissingGithubSecret = chkAllowMissingGh ? chkAllowMissingGh.checked : false;

    try {
      const applyResult = await applyBootstrap({
        githubToken,
        allowMissingGithubSecret,
      });

      modalContainer.innerHTML = `
        <div class="plan-modal-overlay">
          <div class="plan-modal-card" style="max-width: 36rem;">
            <div class="plan-modal-header">
              <h3 class="plan-modal-title">Bootstrap Applied</h3>
              <button type="button" class="btn btn-sm btn-done" title="Close">✕</button>
            </div>
            <div class="plan-modal-body">
              <div class="notice success" style="margin-bottom: 1rem;">
                Prerequisite AWS resources bootstrapped successfully.
              </div>
              <div style="font-size: 0.8125rem;">
                <strong>Actions taken:</strong>
                <ul style="margin: 0.5rem 0 0 1.25rem; padding: 0;">
                  ${(applyResult.actionsTaken || []).map((act) => `<li>${escapeHtml(act)}</li>`).join("")}
                </ul>
              </div>
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
          if (onRefresh) onRefresh();
        });
      });
    } catch (err) {
      btnExecute.disabled = false;
      btnExecute.innerHTML = `<span>Confirm &amp; Apply</span>`;
      modalAlert.innerHTML = `
        <div class="notice error">
          ${escapeHtml(err.message || "Failed to apply bootstrap.")}
        </div>
      `;
    }
  });
}
