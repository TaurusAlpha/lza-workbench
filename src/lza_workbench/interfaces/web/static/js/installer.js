import { getInstallerPlan, saveInstallerSettings } from "./api.js";
import { card, escapeHtml, formatFieldValue, renderBadge } from "./overview.js";

const FORM_SECTIONS = [
  {
    id: "source-repo",
    title: "Source & Repository",
    description: "Configuration repository source location, repository name, and branch settings.",
    fields: [
      "RepositorySource",
      "RepositoryOwner",
      "RepositoryName",
      "RepositoryBranchName",
      "RepositoryBucketName",
      "RepositoryBucketObject",
    ],
  },
  {
    id: "mandatory-accounts",
    title: "Mandatory Accounts",
    description: "Required AWS core account email addresses for the landing zone.",
    fields: [
      "ManagementAccountEmail",
      "LogArchiveAccountEmail",
      "AuditAccountEmail",
    ],
  },
  {
    id: "arch-env",
    title: "Architecture & Environment",
    description: "Landing Zone Accelerator resource prefix and AWS Control Tower integration.",
    fields: [
      "AcceleratorPrefix",
      "ControlTowerEnabled",
    ],
  },
  {
    id: "pipeline-ops",
    title: "Pipeline & Operations",
    description: "Deployment pipeline manual approval gates, notifications, and diagnostics.",
    fields: [
      "EnableApprovalStage",
      "ApprovalStageNotifyEmailList",
      "EnableDiagnosticsPack",
    ],
  },
];

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

export function renderInstallerDetails(container, installerData, onRefresh) {
  const { deployed, canonicalSettings, alignment, pipeline, form, aws } = installerData;

  // 1. Deployed Stack Summary Fields
  const cfnStatus = deployed.stackStatus || (deployed.exists ? "EXISTS" : "NOT_DEPLOYED");
  const driftCount = Object.keys(alignment.configurationDrift || {}).length;
  const driftDisplay = driftCount === 0 ? "None" : `${driftCount} drifted parameter${driftCount === 1 ? "" : "s"}`;

  const deployedFields = [
    ["Stack Name", deployed.stackName, { mono: true, truncate: true }],
    ["Stack Status", cfnStatus, { statusIndicator: Boolean(cfnStatus) }],
    ["Deployed Version", deployed.deployedVersion, { mono: true }],
    ["State Alignment", alignment.status, { statusIndicator: true }],
    ["Configuration Drift", driftDisplay, { statusIndicator: driftCount > 0 }],
    ["Stack ID", deployed.stackId, { mono: true, truncate: true }],
    ["Last Updated", formatTimestamp(deployed.lastUpdatedTime || deployed.creationTime)],
  ];

  // 2. Current Configuration Summary Fields (Bug 3: renamed from Canonical Settings to Current Settings)
  const canonicalFields = [
    ["Source Type", canonicalSettings.repositorySource?.toUpperCase() || "—", { mono: true }],
    ["Repository Name", canonicalSettings.repositoryName || "—", { mono: true }],
    ["Branch", canonicalSettings.repositoryBranch || "—", { mono: true }],
    ["Accelerator Prefix", canonicalSettings.acceleratorPrefix || "—", { mono: true }],
    ["Management Email", canonicalSettings.managementAccountEmail || "—", { mono: true, truncate: true }],
    ["Log Archive Email", canonicalSettings.logArchiveAccountEmail || "—", { mono: true, truncate: true }],
    ["Security Audit Email", canonicalSettings.auditAccountEmail || "—", { mono: true, truncate: true }],
    ["Control Tower", canonicalSettings.controlTowerEnabled ? "Enabled" : "Disabled"],
    ["Approval Stage", canonicalSettings.enableApprovalStage ? "Enabled" : "Disabled"],
  ];

  // 3. Pipeline Fields
  const pipelineFields = [
    ["Pipeline Name", pipeline.name, { mono: true, truncate: true }],
    ["Latest Execution", pipeline.status, { statusIndicator: Boolean(pipeline.status) }],
    ["Current Work", [pipeline.currentStage, pipeline.currentAction].filter(Boolean).join(" / ") || null, { truncate: true }],
    ["Failure", pipeline.failureSummary, { truncate: true }],
  ];

  // Drift Warning Banner if drift detected
  let driftBannerHtml = "";
  if (driftCount > 0) {
    const driftItems = Object.entries(alignment.configurationDrift)
      .map(([param, diff]) => `
        <div class="drift-item">
          <span class="drift-param mono-val">${escapeHtml(param)}</span>:
          <span class="drift-deployed">Deployed: <code>${escapeHtml(diff.deployed)}</code></span> &rarr;
          <span class="drift-target">Configured: <code>${escapeHtml(diff.target)}</code></span>
        </div>
      `)
      .join("");

    driftBannerHtml = `
      <section class="diagnostic-panel diagnostic-panel-warning" style="margin-bottom: 1.5rem;">
        <div class="diagnostic-header">
          <span class="badge badge-warning"><span class="badge-dot" aria-hidden="true"></span>Drift Detected</span>
          <h2 class="diagnostic-title">Configuration Drift (${driftCount})</h2>
        </div>
        <div class="drift-list">${driftItems}</div>
      </section>
    `;
  }

  // 4. Build Dynamic Settings Form Fields (Bug 4: Section-grouped Layout)
  const currentParams = form.resolvedParameters || {};
  const fieldHtmlMap = {};

  form.fields.forEach((field) => {
    const fieldId = `installer-field-${escapeHtml(field.name)}`;
    const currentValue = currentParams[field.name] ?? field.default ?? "";
    const requiredMark = field.required ? '<span class="required-indicator" title="Required">*</span>' : '<span class="required-indicator" style="display:none;" title="Required">*</span>';
    const helpText = field.description
      ? `<p class="form-help">${escapeHtml(field.description)}</p>`
      : "";

    let inputControlHtml = "";
    if (field.allowedValues && field.allowedValues.length > 0) {
      const optionsHtml = field.allowedValues
        .map((opt) => {
          const selected = String(opt) === String(currentValue) ? " selected" : "";
          return `<option value="${escapeHtml(opt)}"${selected}>${escapeHtml(opt)}</option>`;
        })
        .join("");
      inputControlHtml = `
        <select id="${fieldId}" name="${escapeHtml(field.name)}" class="form-select"${field.required ? " required" : ""}>
          ${optionsHtml}
        </select>
      `;
    } else {
      const patternAttr = field.allowedPattern ? ` data-pattern="${escapeHtml(field.allowedPattern)}"` : "";
      inputControlHtml = `
        <input
          type="text"
          id="${fieldId}"
          name="${escapeHtml(field.name)}"
          value="${escapeHtml(currentValue)}"
          class="form-input"
          ${patternAttr}
          ${field.required ? "required" : ""}
        />
      `;
    }

    fieldHtmlMap[field.name] = `
      <div class="form-group" data-field-name="${escapeHtml(field.name)}">
        <label for="${fieldId}" class="form-label">
          ${escapeHtml(field.label || field.name)} ${requiredMark}
        </label>
        ${inputControlHtml}
        ${helpText}
        <div class="form-field-error" id="error-${fieldId}" hidden></div>
      </div>
    `;
  });

  // Render configured sections
  const assignedFieldNames = new Set();
  const renderedSectionsHtml = FORM_SECTIONS.map((section) => {
    const fieldsInSec = section.fields
      .filter((name) => Boolean(fieldHtmlMap[name]))
      .map((name) => {
        assignedFieldNames.add(name);
        return fieldHtmlMap[name];
      })
      .join("");

    if (!fieldsInSec) return "";

    return `
      <div class="form-section" id="section-${escapeHtml(section.id)}">
        <div class="form-section-header">
          <h3 class="form-section-title">${escapeHtml(section.title)}</h3>
          <p class="form-section-desc">${escapeHtml(section.description)}</p>
        </div>
        <div class="form-section-body">
          ${fieldsInSec}
        </div>
      </div>
    `;
  }).join("");

  // Check for any unassigned fields
  const unassignedFieldsHtml = form.fields
    .filter((f) => !assignedFieldNames.has(f.name) && Boolean(fieldHtmlMap[f.name]))
    .map((f) => fieldHtmlMap[f.name])
    .join("");

  const extraSectionHtml = unassignedFieldsHtml
    ? `
      <div class="form-section" id="section-additional">
        <div class="form-section-header">
          <h3 class="form-section-title">Additional Parameters</h3>
          <p class="form-section-desc">Additional CloudFormation parameters defined in the template.</p>
        </div>
        <div class="form-section-body">
          ${unassignedFieldsHtml}
        </div>
      </div>
    `
    : "";

  // Construct whole page layout (Bug 3: "Current Settings" card title)
  container.innerHTML = `
    <div class="installer-view">
      <!-- Summary Cards -->
      <section class="card-grid" style="margin-bottom: 1.5rem;">
        ${card("Deployed Stack", deployedFields, deployed.exists ? "Deployed" : "Not Deployed")}
        ${card("Current Settings", canonicalFields, canonicalSettings.lzaVersion)}
        ${card("Installer Pipeline", pipelineFields, pipeline.status)}
      </section>

      ${driftBannerHtml}

      <!-- Settings & Form Section (Bug 4: structured sections) -->
      <section class="card installer-settings-card">
        <div class="card-header">
          <div>
            <h2 class="card-title">Installer Parameters &amp; Settings</h2>
            <p class="section-subtitle">Parameters derived from the installer CloudFormation template. Changes will be validated before saving to <code>lza-workspace.yaml</code>.</p>
          </div>
        </div>
        <div class="card-body">
          <div id="installer-form-alert" aria-live="polite"></div>
          <form id="installer-settings-form" novalidate>
            <div class="form-sections-container">
              ${renderedSectionsHtml}
              ${extraSectionHtml}
            </div>

            <div class="form-actions" style="margin-top: 1.75rem;">
              <button type="submit" id="btn-save-installer" class="btn btn-primary">
                <span>Save Settings</span>
              </button>
              <button type="button" id="btn-reset-installer" class="btn">
                <span>Reset</span>
              </button>
              <button type="button" id="btn-preview-installer-plan" class="btn btn-secondary">
                <span>Preview Deployment Plan</span>
              </button>
            </div>
          </form>
        </div>
      </section>

      <!-- Deployment Plan Modal Container -->
      <div id="installer-plan-modal-container" hidden></div>

      <!-- Reset Confirmation Modal Container (Bug 6) -->
      <div id="installer-reset-modal-container" hidden></div>
    </div>
  `;

  // Attach Event Handlers
  const formElement = container.querySelector("#installer-settings-form");
  const formAlert = container.querySelector("#installer-form-alert");
  const btnSave = container.querySelector("#btn-save-installer");
  const btnReset = container.querySelector("#btn-reset-installer");
  const btnPreview = container.querySelector("#btn-preview-installer-plan");
  const planContainer = container.querySelector("#installer-plan-modal-container");
  const resetModalContainer = container.querySelector("#installer-reset-modal-container");

  function clearErrors() {
    formAlert.innerHTML = "";
    container.querySelectorAll(".form-field-error").forEach((el) => {
      el.textContent = "";
      el.hidden = true;
    });
    container.querySelectorAll(".form-input, .form-select").forEach((el) => {
      el.classList.remove("has-error");
    });
  }

  function setFieldVisibility(fieldName, isVisible, isRequired) {
    const group = container.querySelector(`.form-group[data-field-name="${fieldName}"]`);
    if (!group) return;
    const input = group.querySelector("input, select");
    const errorEl = group.querySelector(".form-field-error");
    const reqIndicator = group.querySelector(".required-indicator");

    if (isVisible) {
      group.classList.remove("form-group-hidden");
      if (input) {
        input.disabled = false;
        if (isRequired) {
          input.setAttribute("required", "");
          if (reqIndicator) reqIndicator.style.display = "";
        } else {
          input.removeAttribute("required");
          if (reqIndicator) reqIndicator.style.display = "none";
        }
      }
    } else {
      group.classList.add("form-group-hidden");
      if (input) {
        input.disabled = true;
        input.removeAttribute("required");
        input.classList.remove("has-error");
      }
      if (reqIndicator) reqIndicator.style.display = "none";
      if (errorEl) {
        errorEl.textContent = "";
        errorEl.hidden = true;
      }
    }
  }

  function updateFieldVisibility() {
    // 1. Repository Source conditional visibility
    const repoSourceEl = container.querySelector("#installer-field-RepositorySource");
    const repoSource = (repoSourceEl ? repoSourceEl.value : "codecommit").toLowerCase();

    if (repoSource === "github") {
      setFieldVisibility("RepositoryOwner", true, true);
      setFieldVisibility("RepositoryName", true, true);
      setFieldVisibility("RepositoryBranchName", true, true);
      setFieldVisibility("RepositoryBucketName", false, false);
      setFieldVisibility("RepositoryBucketObject", false, false);
    } else if (repoSource === "s3") {
      setFieldVisibility("RepositoryOwner", false, false);
      setFieldVisibility("RepositoryName", false, false);
      setFieldVisibility("RepositoryBranchName", false, false);
      setFieldVisibility("RepositoryBucketName", true, true);
      setFieldVisibility("RepositoryBucketObject", true, true);
    } else {
      // codecommit or codeconnection
      setFieldVisibility("RepositoryOwner", false, false);
      setFieldVisibility("RepositoryName", true, true);
      setFieldVisibility("RepositoryBranchName", true, true);
      setFieldVisibility("RepositoryBucketName", false, false);
      setFieldVisibility("RepositoryBucketObject", false, false);
    }

    // 2. EnableApprovalStage conditional visibility
    const approvalEl = container.querySelector("#installer-field-EnableApprovalStage");
    const approvalVal = approvalEl ? approvalEl.value : "No";
    const approvalEnabled = approvalVal === "Yes";
    setFieldVisibility("ApprovalStageNotifyEmailList", approvalEnabled, approvalEnabled);
  }

  function validateForm() {
    clearErrors();
    let hasError = false;
    const values = {};

    form.fields.forEach((field) => {
      const group = container.querySelector(`.form-group[data-field-name="${field.name}"]`);
      if (!group || group.classList.contains("form-group-hidden")) {
        return; // skip hidden fields from validation
      }
      const fieldId = `installer-field-${field.name}`;
      const input = container.querySelector(`#${fieldId}`);
      if (!input || input.disabled) return;

      const val = input.value.trim();
      values[field.name] = val;

      const errorEl = container.querySelector(`#error-${fieldId}`);
      const isRequired = input.hasAttribute("required");

      if (isRequired && !val) {
        hasError = true;
        input.classList.add("has-error");
        if (errorEl) {
          errorEl.textContent = `${field.label || field.name} is required.`;
          errorEl.hidden = false;
        }
        return;
      }

      const pattern = input.dataset.pattern;
      if (pattern && val) {
        try {
          const regex = new RegExp(`^${pattern}$`);
          if (!regex.test(val)) {
            hasError = true;
            input.classList.add("has-error");
            if (errorEl) {
              errorEl.textContent = `Does not match the required pattern (${pattern}).`;
              errorEl.hidden = false;
            }
            return;
          }
        } catch {
          // If regex pattern from CloudFormation isn't directly constructible in JS, fallback to server validation
        }
      }
    });

    return { isValid: !hasError, values };
  }

  // Reactive visibility updates on change/input
  formElement.addEventListener("change", () => {
    updateFieldVisibility();
  });
  formElement.addEventListener("input", () => {
    updateFieldVisibility();
  });
  // Run initial visibility update to reflect current loaded state
  updateFieldVisibility();

  // Handle Form Submission / Save
  formElement.addEventListener("submit", async (e) => {
    e.preventDefault();
    const { isValid, values } = validateForm();

    if (!isValid) {
      formAlert.innerHTML = `
        <div class="notice error">
          Please correct the highlighted validation errors before saving.
        </div>
      `;
      return;
    }

    btnSave.disabled = true;
    formAlert.innerHTML = `
      <div class="notice info">
        Saving installer settings&hellip;
      </div>
    `;

    try {
      const saveRes = await saveInstallerSettings(values);
      if (saveRes && saveRes.resolvedParameters) {
        Object.assign(currentParams, saveRes.resolvedParameters);
      }
      formAlert.innerHTML = `
        <div class="notice success">
          Installer settings saved successfully.
        </div>
      `;
      if (typeof onRefresh === "function") {
        setTimeout(() => onRefresh(), 800);
      }
    } catch (err) {
      formAlert.innerHTML = `
        <div class="notice error">
          ${escapeHtml(err.message)}
        </div>
      `;
    } finally {
      btnSave.disabled = false;
    }
  });

  // Handle Reset Modal: Revert form fields to written configuration in lza-workspace.yaml
  function showResetModal() {
    resetModalContainer.hidden = false;
    resetModalContainer.innerHTML = `
      <div class="plan-modal-overlay">
        <div class="plan-modal-card" style="max-width: 32rem;">
          <div class="plan-modal-header">
            <h3 class="plan-modal-title">Reset Installer Form</h3>
            <button type="button" class="btn btn-sm btn-close-reset" title="Cancel">✕</button>
          </div>
          <div class="plan-modal-body">
            <p style="margin-bottom: 0.75rem; line-height: 1.5;">
              Are you sure you want to reset all form settings?
            </p>
            <div class="notice info" style="margin-bottom: 0.75rem;">
              Form inputs will be reverted to the written configuration from <code>lza-workspace.yaml</code>. All unsaved changes will be discarded.
            </div>
          </div>
          <div class="plan-modal-footer" style="gap: 0.75rem;">
            <button type="button" class="btn btn-close-reset">Cancel</button>
            <button type="button" id="btn-confirm-revert" class="btn btn-primary">Reset to Written Settings</button>
          </div>
        </div>
      </div>
    `;

    const closeButtons = resetModalContainer.querySelectorAll(".btn-close-reset");
    closeButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        resetModalContainer.hidden = true;
        resetModalContainer.innerHTML = "";
      });
    });

    const confirmBtn = resetModalContainer.querySelector("#btn-confirm-revert");

    confirmBtn.addEventListener("click", () => {
      resetModalContainer.hidden = true;
      resetModalContainer.innerHTML = "";
      clearErrors();

      // Revert each input to written configuration parameter from lza-workspace.yaml
      form.fields.forEach((field) => {
        const fieldId = `installer-field-${field.name}`;
        const input = container.querySelector(`#${fieldId}`);
        if (input) {
          input.value = currentParams[field.name] ?? "";
        }
      });

      // Reactively update conditional fields visibility
      updateFieldVisibility();

      formAlert.innerHTML = `
        <div class="notice info">
          Form values reset to written configuration from <code>lza-workspace.yaml</code>.
        </div>
      `;
      setTimeout(() => {
        if (formAlert.querySelector(".info")) formAlert.innerHTML = "";
      }, 2500);
    });
  }

  btnReset.addEventListener("click", () => {
    showResetModal();
  });

  // Handle Preview Deployment Plan
  btnPreview.addEventListener("click", async () => {
    btnPreview.disabled = true;
    planContainer.hidden = false;
    planContainer.innerHTML = `
      <div class="plan-modal-overlay">
        <div class="plan-modal-card">
          <div class="plan-modal-header">
            <h3 class="plan-modal-title">Generating Deployment Plan&hellip;</h3>
          </div>
          <div class="plan-modal-body">
            <p class="plan-loading-text">Inspecting AWS CloudFormation stack and CodeCommit source repository&hellip;</p>
          </div>
        </div>
      </div>
    `;

    try {
      const planResult = await getInstallerPlan();
      renderPlanPreview(planContainer, planResult);
    } catch (err) {
      planContainer.innerHTML = `
        <div class="plan-modal-overlay">
          <div class="plan-modal-card">
            <div class="plan-modal-header">
              <h3 class="plan-modal-title">Deployment Plan Error</h3>
              <button type="button" class="btn btn-sm btn-close-plan">Close</button>
            </div>
            <div class="plan-modal-body">
              <div class="notice error">${escapeHtml(err.message)}</div>
            </div>
          </div>
        </div>
      `;
      planContainer.querySelector(".btn-close-plan")?.addEventListener("click", () => {
        planContainer.hidden = true;
        planContainer.innerHTML = "";
      });
    } finally {
      btnPreview.disabled = false;
    }
  });
}

function renderPlanPreview(container, plan) {
  const cfn = plan.cloudformation;
  const cc = plan.codecommit;
  const diffs = cfn.parameterDiffs || {};
  const diffEntries = Object.entries(diffs);

  let diffTableHtml = "";
  if (diffEntries.length === 0) {
    diffTableHtml = `<p class="plan-empty-text">No parameter changes detected between deployed CloudFormation stack and local configuration.</p>`;
  } else {
    const rows = diffEntries
      .map(
        ([param, diff]) => `
        <tr>
          <td class="mono-val" style="font-weight: 600;">${escapeHtml(param)}</td>
          <td class="mono-val">${escapeHtml(diff.deployed ?? "—")}</td>
          <td class="mono-val font-accent">${escapeHtml(diff.target ?? "—")}</td>
        </tr>
      `
      )
      .join("");

    diffTableHtml = `
      <div class="table-container" style="margin-top: 0.75rem;">
        <table class="plan-diff-table">
          <thead>
            <tr>
              <th>Parameter</th>
              <th>Current Deployed Value</th>
              <th>Target Value</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    `;
  }

  const ghWarning = plan.githubSecretWarning
    ? `<div class="notice warning" style="margin-top: 1rem;">${escapeHtml(plan.githubSecretWarning)}</div>`
    : "";

  container.innerHTML = `
    <div class="plan-modal-overlay">
      <div class="plan-modal-card">
        <div class="plan-modal-header">
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <h3 class="plan-modal-title">Installer Deployment Plan</h3>
              <span class="badge badge-${cfn.operation === "NO_CHANGE" ? "success" : "warning"}">${escapeHtml(cfn.operation)}</span>
            </div>
            <p class="section-subtitle">Read-only preview of CloudFormation and repository actions.</p>
          </div>
          <button type="button" class="btn btn-sm btn-close-plan" title="Close Preview">✕</button>
        </div>
        <div class="plan-modal-body">
          <div class="plan-summary-grid">
            <div class="plan-summary-item">
              <span class="plan-summary-label">Target Stack</span>
              <span class="mono-val">${escapeHtml(cfn.stackName)}</span>
            </div>
            <div class="plan-summary-item">
              <span class="plan-summary-label">Stack Status</span>
              <span>${escapeHtml(cfn.stackStatus || "DOES_NOT_EXIST")}</span>
            </div>
            <div class="plan-summary-item">
              <span class="plan-summary-label">Source Status</span>
              <span>${escapeHtml(cc.status || "N/A")}</span>
            </div>
          </div>

          <h4 style="margin: 1.25rem 0 0.5rem 0; font-size: 0.875rem; font-weight: 600;">CloudFormation Parameter Changes (${diffEntries.length})</h4>
          ${diffTableHtml}

          ${ghWarning}

          <div class="notice info" style="margin-top: 1.25rem;">
            <strong>Deployment mutation is disabled in this preview.</strong><br>
            To execute this deployment, run <code>lza installer deploy</code> from your terminal.
          </div>
        </div>
        <div class="plan-modal-footer">
          <button type="button" class="btn btn-close-plan">Close Preview</button>
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll(".btn-close-plan").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.hidden = true;
      container.innerHTML = "";
    });
  });
}
