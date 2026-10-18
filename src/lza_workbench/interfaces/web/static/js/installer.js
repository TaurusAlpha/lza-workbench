import { getInstallerPlan, resetInstallerSettings, saveInstallerSettings } from "./api.js";
import { card, escapeHtml } from "./overview.js";

const FORM_SECTIONS = [
  {
    id: "source-repo",
    title: "Installer Engine Source",
    description: "LZA engine source code location, repository name, and branch settings.",
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
    id: "config-repo",
    title: "Customer Configuration Repository",
    description: "Repository hosting the customer landing zone configuration files (accounts-config, etc.).",
    fields: [
      "ConfigurationRepositoryLocation",
      "UseExistingConfigRepo",
      "ExistingConfigRepositoryName",
      "ExistingConfigRepositoryBranchName",
      "ExistingConfigRepositoryOwner",
      "ConfigCodeConnectionArn",
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

export function hasUnsavedInstallerChanges(container) {
  return container.querySelector("#installer-settings-form")?.dataset.dirty === "true";
}

export function confirmDiscardInstallerChanges(container) {
  if (!hasUnsavedInstallerChanges(container)) return true;
  if (!confirm("Discard unsaved installer edits?")) return false;
  const form = container.querySelector("#installer-settings-form");
  form.reset();
  form.dataset.dirty = "false";
  return true;
}

export function renderInstallerDetails(container, installerData, onRefresh) {
  const { deployed, canonicalSettings, alignment, pipeline, form, aws } = installerData;

  const comparison = alignment.parameterComparison || "Not checked";
  const stackIsLive = aws.isLive && !deployed.error;
  const stackLabel = stackIsLive ? (deployed.exists ? "Deployed" : "Not deployed") : "Recorded stack";
  const comparisonVariant = comparison === "No pending changes" ? "success" : comparison === "Not checked" ? "neutral" : "warning";

  // 1. Deployed Stack Summary Fields
  const cfnStatus = deployed.stackStatus || (deployed.exists ? "EXISTS" : "NOT_DEPLOYED");
  const driftCount = Object.keys(alignment.configurationDrift || {}).length;

  const deployedFields = [
    ["Stack Name", deployed.stackName, { mono: true, copy: true, copyLabel: "Copy stack name" }],
    ["Stack Status", stackIsLive ? cfnStatus : `Recorded: ${cfnStatus}`, { statusIndicator: Boolean(cfnStatus) }],
    ["Deployed Version", deployed.deployedVersion, { mono: true }],
    ["Recorded metadata", stackIsLive ? alignment.status : "Not checked", { statusIndicator: true }],
    ["Saved vs deployed", comparison],
    ["Stack ID", deployed.stackId, { mono: true, copy: Boolean(deployed.stackId), copyLabel: "Copy stack ID" }],
    ["Last Updated", formatTimestamp(deployed.lastUpdatedTime || deployed.creationTime)],
  ];

  // 2. Current Configuration Summary Fields
  const canonicalFields = [
    ["Engine Source", canonicalSettings.repositorySource?.toUpperCase() || "—", { mono: true }],
    ["Engine Branch", canonicalSettings.repositoryBranch || "—", { mono: true }],
    ["Config Location", canonicalSettings.configRepositoryLocation?.toUpperCase() || "—", { mono: true }],
    ["Config Repo Name", canonicalSettings.configRepositoryName || (canonicalSettings.configRepositoryLocation === "s3" ? "(S3 Bucket)" : "—"), { mono: true }],
    ["Accelerator Prefix", canonicalSettings.acceleratorPrefix || "—", { mono: true }],
    ["Management Email", canonicalSettings.managementAccountEmail || "—", { mono: true, copy: Boolean(canonicalSettings.managementAccountEmail), copyLabel: "Copy management email" }],
    ["Log Archive Email", canonicalSettings.logArchiveAccountEmail || "—", { mono: true, copy: Boolean(canonicalSettings.logArchiveAccountEmail), copyLabel: "Copy log archive email" }],
    ["Security Audit Email", canonicalSettings.auditAccountEmail || "—", { mono: true, copy: Boolean(canonicalSettings.auditAccountEmail), copyLabel: "Copy security audit email" }],
    ["Control Tower", canonicalSettings.controlTowerEnabled ? "Enabled" : "Disabled"],
    ["Approval Stage", canonicalSettings.enableApprovalStage ? "Enabled" : "Disabled"],
  ];

  const pipelineStatus = pipeline.isLive ? pipeline.status : `Recorded: ${pipeline.status || "Not checked"}`;
  const pipelineFields = [
    ["Pipeline name", pipeline.name, { mono: true, copy: true, copyLabel: "Copy installer pipeline name" }],
    ["Latest run", pipelineStatus, { statusIndicator: Boolean(pipeline.status) }],
    ["Started", pipeline.startTime ? formatTimestamp(pipeline.startTime) : "Time unavailable"],
    ...(pipeline.currentStage || pipeline.currentAction ? [["Current work", [pipeline.currentStage, pipeline.currentAction].filter(Boolean).join(" / ")]] : []),
    ...(pipeline.failureSummary ? [["Failure", pipeline.failureSummary]] : []),
  ];

  // Drift Warning Banner if drift detected
  let driftBannerHtml = "";
  if (driftCount > 0) {
    const driftItems = Object.entries(alignment.configurationDrift)
      .map(([param, diff]) => `
        <div class="drift-item">
          <span class="drift-param mono-val">${escapeHtml(param)}</span>:
          <span class="drift-deployed">Deployed: <code>${escapeHtml(diff.deployed)}</code></span> &rarr;
          <span class="drift-target">Saved: <code>${escapeHtml(diff.target)}</code></span>
        </div>
      `)
      .join("");

    driftBannerHtml = `
      <section class="diagnostic-panel diagnostic-panel-warning">
        <div class="diagnostic-header">
          <span class="badge badge-warning"><span class="badge-dot" aria-hidden="true"></span>Saved settings differ</span>
          <h2 class="diagnostic-title">Saved versus deployed parameters (${driftCount})</h2>
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
    const description = field.description || "";
    const warning = description.match(/(?:NOTE:|Note:)[\s\S]*/)?.[0] || "";
    const hint = description.replace(warning, "").trim().replace(/-\s*$/, "");
    const helpText = description ? `<div class="form-help" id="help-${fieldId}">
      ${hint ? `<p>${escapeHtml(hint)}</p>` : ""}
      ${warning ? `<p class="installer-field-warning">${escapeHtml(warning)}</p>` : ""}
    </div>` : "";

    let inputControlHtml = "";
    if (field.allowedValues && field.allowedValues.length > 0) {
      const optionsHtml = field.allowedValues
        .map((opt) => {
          const selected = String(opt) === String(currentValue) ? " selected" : "";
          return `<option value="${escapeHtml(opt)}"${selected}>${escapeHtml(opt)}</option>`;
        })
        .join("");
      inputControlHtml = `
        <select id="${fieldId}" name="${escapeHtml(field.name)}" class="form-select" aria-describedby="help-${fieldId} error-${fieldId}"${field.required ? " required" : ""}>
          ${optionsHtml}
        </select>
      `;
    } else {
      const patternAttr = field.allowedPattern ? ` data-pattern="${escapeHtml(field.allowedPattern)}"` : "";
      const isEmail = field.name.toLowerCase().includes("email") && !field.name.toLowerCase().includes("list");
      const inputType = isEmail ? "email" : "text";
      inputControlHtml = `
        <input
          type="${inputType}"
          id="${fieldId}"
          name="${escapeHtml(field.name)}"
          value="${escapeHtml(currentValue)}"
          class="form-input"
          aria-describedby="help-${fieldId} error-${fieldId}"
          ${patternAttr}
          ${field.required ? "required" : ""}
        />
      `;
    }

    const driftDiff = (alignment.configurationDrift || {})[field.name];
    const driftBadge = driftDiff
      ? `<span class="param-pending-badge" title="Deployed: ${escapeHtml(driftDiff.deployed ?? "—")} &rarr; Configured: ${escapeHtml(driftDiff.target ?? "—")}">Saved difference</span>`
      : "";
    const pendingClass = driftDiff ? " has-pending-change" : "";

    fieldHtmlMap[field.name] = `
      <div class="form-group${pendingClass}" data-field-name="${escapeHtml(field.name)}">
        <label for="${fieldId}" class="form-label">
          ${escapeHtml(field.label || field.name)} ${requiredMark} ${driftBadge}
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
      <section class="installer-summary-grid">
        ${card("Deployed stack", deployedFields, stackLabel)}
        ${card("Saved workspace settings", canonicalFields, canonicalSettings.lzaVersion)}
      </section>
      <section class="installer-comparison notice ${comparisonVariant === "warning" ? "warning" : "info"}" aria-label="Saved versus deployed stack settings">
        <strong class="badge badge-${comparisonVariant}">${escapeHtml(comparison)}</strong>
        <span>${comparison === "No pending changes" ? "Saved parameters match the live stack." : comparison === "Not checked" ? "Live stack parameters could not be compared." : "Review saved and deployed values below."}</span>
      </section>
      <section class="installer-pipeline-summary">
        ${card("Installer pipeline", pipelineFields, pipelineStatus, { href: "#/pipeline/installer" })}
      </section>

      ${driftBannerHtml}

      <!-- Settings & Form Section (Bug 4: structured sections) -->
      <section class="card installer-settings-card">
        <nav class="installer-section-nav" aria-label="Installer settings sections">
          ${FORM_SECTIONS.filter(section => section.fields.some(name => fieldHtmlMap[name])).map(section => `<button type="button" class="btn btn-sm btn-ghost" data-section="section-${section.id}">${escapeHtml(section.title)}</button>`).join("")}
          ${unassignedFieldsHtml ? '<button type="button" class="btn btn-sm btn-ghost" data-section="section-additional">Additional parameters</button>' : ""}
        </nav>
        <div class="card-header">
          <div>
            <div style="display: flex; align-items: center; gap: 0.625rem;">
              <h2 class="card-title">Installer Parameters &amp; Settings</h2>
              <span id="installer-dirty-badge" class="badge badge-warning" style="display:none; font-size: 0.75rem;">Unsaved Changes</span>
            </div>
            <p class="section-subtitle">Save updates <code>lza-workspace.yaml</code>. It does not deploy the stack.</p>
          </div>
        </div>
        <div class="card-body">
          <div id="installer-form-alert" aria-live="polite"></div>
          <form id="installer-settings-form" data-dirty="false" novalidate>
            <div class="form-sections-container">
              ${renderedSectionsHtml}
              ${extraSectionHtml}
            </div>

            <div class="form-actions installer-actions">
              <button type="submit" id="btn-save-installer" class="btn btn-primary">
                <span>Save Settings</span>
              </button>
              <button type="button" id="btn-reset-installer" class="btn">
                <span>Discard unsaved edits</span>
              </button>
              <button type="button" id="btn-restore-installer" class="btn btn-secondary" ${!stackIsLive || !deployed.exists || !Object.keys(deployed.deployedParameters || {}).length || driftCount === 0 ? "disabled" : ""}>Restore deployed settings</button>
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
  const btnRestore = container.querySelector("#btn-restore-installer");
  const btnPreview = container.querySelector("#btn-preview-installer-plan");
  const planContainer = container.querySelector("#installer-plan-modal-container");
  const resetModalContainer = container.querySelector("#installer-reset-modal-container");
  let saving = false;

  function clearErrors() {
    formAlert.innerHTML = "";
    container.querySelectorAll(".form-field-error").forEach((el) => {
      el.textContent = "";
      el.hidden = true;
    });
    container.querySelectorAll(".form-input, .form-select").forEach((el) => {
      el.classList.remove("has-error");
      el.removeAttribute("aria-invalid");
    });
  }

  function setFieldVisibility(fieldName, isVisible, isRequired) {
    const group = container.querySelector(`.form-group[data-field-name="${fieldName}"]`);
    if (!group) return;
    const input = group.querySelector("input, select");
    const errorEl = group.querySelector(".form-field-error");
    const reqIndicator = group.querySelector(".required-indicator");

    if (isVisible) {
      group.hidden = false;
      group.style.display = "";
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
      group.hidden = true;
      group.style.display = "none";
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
    // 1. Installer Engine Source (RepositorySource)
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
    } else if (repoSource === "codeconnection") {
      setFieldVisibility("RepositoryOwner", true, true);
      setFieldVisibility("RepositoryName", true, true);
      setFieldVisibility("RepositoryBranchName", true, true);
      setFieldVisibility("RepositoryBucketName", false, false);
      setFieldVisibility("RepositoryBucketObject", false, false);
    } else {
      // codecommit
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

    // 3. Customer Configuration Repository conditional visibility
    const configLocEl = container.querySelector("#installer-field-ConfigurationRepositoryLocation");
    const configLoc = (configLocEl ? configLocEl.value : "codecommit").toLowerCase();
    const useExistingEl = container.querySelector("#installer-field-UseExistingConfigRepo");
    const useExistingVal = useExistingEl ? useExistingEl.value : "No";
    const isUsingExisting = useExistingVal === "Yes";

    if (configLoc === "s3") {
      // S3 -> all are not relevant
      setFieldVisibility("UseExistingConfigRepo", false, false);
      setFieldVisibility("ExistingConfigRepositoryName", false, false);
      setFieldVisibility("ExistingConfigRepositoryBranchName", false, false);
      setFieldVisibility("ExistingConfigRepositoryOwner", false, false);
      setFieldVisibility("ConfigCodeConnectionArn", false, false);
    } else if (configLoc === "codeconnection") {
      // CodeConnection -> ARN, Owner, Name, Branch are relevant
      setFieldVisibility("UseExistingConfigRepo", false, false);
      setFieldVisibility("ConfigCodeConnectionArn", true, true);
      setFieldVisibility("ExistingConfigRepositoryOwner", true, true);
      setFieldVisibility("ExistingConfigRepositoryName", true, true);
      setFieldVisibility("ExistingConfigRepositoryBranchName", true, true);
    } else {
      // CodeCommit -> CodeConnection ARN and Existing config repo owner are not relevant
      setFieldVisibility("ConfigCodeConnectionArn", false, false);
      setFieldVisibility("ExistingConfigRepositoryOwner", false, false);
      setFieldVisibility("UseExistingConfigRepo", true, true);

      if (isUsingExisting) {
        setFieldVisibility("ExistingConfigRepositoryName", true, true);
        setFieldVisibility("ExistingConfigRepositoryBranchName", true, true);
      } else {
        setFieldVisibility("ExistingConfigRepositoryName", false, false);
        setFieldVisibility("ExistingConfigRepositoryBranchName", false, false);
      }
    }
  }

  const dirtyBadge = container.querySelector("#installer-dirty-badge");

  function checkDirtyState() {
    let isDirty = false;
    form.fields.forEach((field) => {
      const group = container.querySelector(`.form-group[data-field-name="${field.name}"]`);
      const isHidden = !group || group.classList.contains("form-group-hidden") || group.hidden || group.style.display === "none";
      if (isHidden) return;
      const input = container.querySelector(`#installer-field-${field.name}`);
      if (!input || input.disabled) return;
      const initialVal = String(currentParams[field.name] ?? field.default ?? "").trim();
      const currentVal = String(input.value).trim();
      if (initialVal !== currentVal) {
        isDirty = true;
      }
    });
    formElement.dataset.dirty = String(isDirty);
    btnSave.disabled = !isDirty || saving;
    btnReset.disabled = !isDirty || saving;
    btnPreview.disabled = saving;
    if (dirtyBadge) {
      dirtyBadge.style.display = isDirty ? "inline-block" : "none";
    }
  }

  function validateForm() {
    clearErrors();
    let hasError = false;
    const values = {};

    form.fields.forEach((field) => {
      const group = container.querySelector(`.form-group[data-field-name="${field.name}"]`);
      const isHidden = !group || group.classList.contains("form-group-hidden") || group.hidden || group.style.display === "none";
      const fieldId = `installer-field-${field.name}`;
      const input = container.querySelector(`#${fieldId}`);

      if (isHidden) {
        if (field.name === "UseExistingConfigRepo") {
          const configLoc = (container.querySelector("#installer-field-ConfigurationRepositoryLocation")?.value || "").toLowerCase();
          values[field.name] = configLoc === "codeconnection" ? "Yes" : "No";
        } else {
          values[field.name] = "";
        }
        return;
      }

      if (!input || input.disabled) return;

      const val = input.value.trim();
      values[field.name] = val;

      const errorEl = container.querySelector(`#error-${fieldId}`);
      const isRequired = input.hasAttribute("required");

      if (isRequired && !val) {
        hasError = true;
        input.classList.add("has-error");
        input.setAttribute("aria-invalid", "true");
        if (errorEl) {
          errorEl.textContent = `${field.label || field.name} is required.`;
          errorEl.hidden = false;
        }
        return;
      }

      if (input.type === "email" && val) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(val)) {
          hasError = true;
          input.classList.add("has-error");
        input.setAttribute("aria-invalid", "true");
          if (errorEl) {
            errorEl.textContent = "Please enter a valid email address.";
            errorEl.hidden = false;
          }
          return;
        }
      }

      const pattern = input.dataset.pattern;
      if (pattern && val) {
        try {
          const regex = new RegExp(`^${pattern}$`);
          if (!regex.test(val)) {
            hasError = true;
            input.classList.add("has-error");
        input.setAttribute("aria-invalid", "true");
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

  // Clear stale validation feedback as the user edits the affected field.
  function handleFormEdit(event) {
    const input = event.target;
    input.classList.remove("has-error");
    input.removeAttribute("aria-invalid");
    const error = container.querySelector(`#error-${input.id}`);
    if (error) {
      error.textContent = "";
      error.hidden = true;
    }
    if (!formElement.querySelector('[aria-invalid="true"]')) formAlert.innerHTML = "";
    updateFieldVisibility();
    checkDirtyState();
  }
  formElement.addEventListener("reset", () => queueMicrotask(() => {
    clearErrors();
    updateFieldVisibility();
    checkDirtyState();
  }));
  formElement.addEventListener("change", handleFormEdit);
  formElement.addEventListener("input", handleFormEdit);
  // Run initial visibility update to reflect current loaded state
  updateFieldVisibility();
  checkDirtyState();

  async function saveSettings({ refreshAfterSave = true } = {}) {
    if (saving) return false;
    const { isValid, values } = validateForm();

    if (!isValid) {
      formAlert.innerHTML = `
        <div class="notice error">
          Please correct the highlighted validation errors before saving.
        </div>
      `;
      container.querySelector('[aria-invalid="true"]')?.focus();
      return false;
    }

    saving = true;
    checkDirtyState();
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
      form.fields.forEach(field => {
        const input = container.querySelector(`#installer-field-${field.name}`);
        const savedValue = String(currentParams[field.name] ?? field.default ?? "");
        if (input?.tagName === "SELECT") {
          [...input.options].forEach(option => { option.defaultSelected = option.value === savedValue; });
        } else if (input) {
          input.defaultValue = savedValue;
        }
      });
      formElement.dataset.dirty = "false";
      checkDirtyState();
      formAlert.innerHTML = `
        <div class="notice success">
          Installer settings saved successfully.
        </div>
      `;
      if (refreshAfterSave && typeof onRefresh === "function") {
        setTimeout(() => {
          if (formElement.isConnected && !hasUnsavedInstallerChanges(container)) onRefresh();
        }, 800);
      }
      return true;
    } catch (err) {
      formAlert.innerHTML = `
        <div class="notice error">
          ${escapeHtml(err.message)}
        </div>
      `;
      formAlert.tabIndex = -1;
      formAlert.focus();
      return false;
    } finally {
      saving = false;
      checkDirtyState();
    }
  }

  formElement.addEventListener("submit", async event => {
    event.preventDefault();
    await saveSettings();
  });

  let previewRequest = 0;
  let refreshAfterPreview = false;
  let modalTrigger = null;
  function focusModal(modalContainer, trigger) {
    modalTrigger = trigger;
    const dialog = modalContainer.querySelector(".plan-modal-card");
    if (!dialog) return;
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("tabindex", "-1");
    const title = dialog.querySelector(".plan-modal-title");
    title.id = `${modalContainer.id}-title`;
    dialog.setAttribute("aria-labelledby", title.id);
    dialog.focus();
  }

  function closeAllModals() {
    const refreshSavedSettings = refreshAfterPreview;
    refreshAfterPreview = false;
    previewRequest += 1;
    checkDirtyState();
    planContainer.hidden = true;
    planContainer.innerHTML = "";
    resetModalContainer.hidden = true;
    resetModalContainer.innerHTML = "";
    modalTrigger?.focus();
    modalTrigger = null;
    if (refreshSavedSettings && formElement.isConnected && !hasUnsavedInstallerChanges(container)) onRefresh?.();
  }

  [planContainer, resetModalContainer].forEach(modalContainer => {
    modalContainer.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeAllModals();
      } else if (event.key === "Tab") {
        const controls = [...modalContainer.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), summary')].filter(el => el.getClientRects().length);
        const first = controls[0];
        const last = controls.at(-1);
        if (event.shiftKey && (document.activeElement === first || document.activeElement === modalContainer.querySelector(".plan-modal-card"))) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    });
  });

  container.querySelectorAll("[data-section]").forEach(button => button.addEventListener("click", () => {
    container.querySelector(`#${button.dataset.section}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  container.querySelectorAll(".card-interactive").forEach(card => card.addEventListener("click", event => {
    if (!event.target.closest("a, button") && !window.getSelection()?.toString()) window.location.hash = card.dataset.href;
  }));
  container.querySelectorAll(".btn-copy-inline").forEach(button => button.addEventListener("click", async event => {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.classList.add("copied");
      setTimeout(() => button.classList.remove("copied"), 1500);
    } catch (err) {
      formAlert.textContent = `Unable to copy: ${err.message}`;
    }
  }));

  btnReset.addEventListener("click", () => confirmDiscardInstallerChanges(container));

  btnRestore.addEventListener("click", () => {
    closeAllModals();
    const rows = Object.entries(deployed.deployedParameters || {}).filter(([name, value]) => form.fields.some(field => field.name === name) && String(currentParams[name] ?? "") !== String(value ?? "")).map(([name, value]) =>
      `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(currentParams[name] ?? "—")}</td><td>${escapeHtml(value)}</td></tr>`).join("");
    resetModalContainer.hidden = false;
    resetModalContainer.innerHTML = `<div class="plan-modal-overlay"><div class="plan-modal-card">
      <div class="plan-modal-header"><h3 class="plan-modal-title">Restore deployed settings</h3><button type="button" class="btn btn-close-reset" aria-label="Close restore dialog">✕</button></div>
      <div class="plan-modal-body"><p>This replaces saved workspace settings and discards unsaved edits. It does not change AWS.</p>
      <div class="table-container"><table class="plan-diff-table"><thead><tr><th>Parameter</th><th>Saved</th><th>Deployed</th></tr></thead><tbody>${rows}</tbody></table></div><div id="reset-modal-alert" aria-live="polite"></div></div>
      <div class="plan-modal-footer"><button type="button" class="btn btn-close-reset">Cancel</button><button type="button" class="btn btn-primary" id="btn-confirm-revert-deployed">Restore deployed settings</button></div>
    </div></div>`;
    resetModalContainer.querySelectorAll(".btn-close-reset").forEach(btn => btn.addEventListener("click", closeAllModals));
    resetModalContainer.querySelector("#btn-confirm-revert-deployed").addEventListener("click", async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await resetInstallerSettings();
        formElement.dataset.dirty = "false";
        closeAllModals();
        onRefresh?.();
      } catch (err) {
        button.disabled = false;
        resetModalContainer.querySelector("#reset-modal-alert").textContent = err.message;
      }
    });
    focusModal(resetModalContainer, btnRestore);
  });

  // Handle Preview Deployment Plan
  async function previewDeploymentPlan({ refreshOnClose = false } = {}) {
    closeAllModals();
    refreshAfterPreview = refreshOnClose;
    if (hasUnsavedInstallerChanges(container)) {
      planContainer.hidden = false;
      planContainer.innerHTML = `
        <div class="plan-modal-overlay">
          <div class="plan-modal-card">
            <div class="plan-modal-header">
              <h3 class="plan-modal-title">Unsaved settings</h3>
              <button type="button" class="btn btn-close-plan" aria-label="Close warning">✕</button>
            </div>
            <div class="plan-modal-body">
              <p>Save your changes or discard them to preview the deployment plan.</p>
            </div>
            <div class="plan-modal-footer">
              <button type="button" class="btn btn-close-plan">Cancel</button>
              <button type="button" class="btn btn-secondary" id="btn-discard-and-preview">Discard and preview</button>
              <button type="button" class="btn btn-primary" id="btn-save-and-preview">Save and preview</button>
            </div>
          </div>
        </div>`;
      planContainer.querySelectorAll(".btn-close-plan").forEach(button => button.addEventListener("click", closeAllModals));
      planContainer.querySelector("#btn-discard-and-preview").addEventListener("click", async () => {
        formElement.reset();
        clearErrors();
        updateFieldVisibility();
        checkDirtyState();
        await previewDeploymentPlan();
      });
      planContainer.querySelector("#btn-save-and-preview").addEventListener("click", async () => {
        closeAllModals();
        const saved = await saveSettings({ refreshAfterSave: false });
        if (saved && formElement.isConnected) await previewDeploymentPlan({ refreshOnClose: true });
      });
      planContainer.querySelector(".plan-modal-overlay").addEventListener("click", event => {
        if (event.target.classList.contains("plan-modal-overlay")) closeAllModals();
      });
      focusModal(planContainer, btnPreview);
      return;
    }
    const requestId = ++previewRequest;
    btnPreview.disabled = true;
    planContainer.hidden = false;
    planContainer.innerHTML = `
      <div class="plan-modal-overlay">
        <div class="plan-modal-card">
          <div class="plan-modal-header">
            <h3 class="plan-modal-title">Generating Deployment Plan&hellip;</h3>
            <button type="button" class="btn btn-close-plan" title="Cancel">✕</button>
          </div>
          <div class="plan-modal-body">
            <p class="plan-loading-text">Inspecting AWS CloudFormation stack and CodeCommit source repository&hellip;</p>
          </div>
        </div>
      </div>
    `;

    focusModal(planContainer, btnPreview);
    planContainer.querySelector(".btn-close-plan")?.addEventListener("click", closeAllModals);

    const overlay = planContainer.querySelector(".plan-modal-overlay");
    overlay?.addEventListener("click", (e) => {
      if (e.target === overlay) {
        closeAllModals();
      }
    });

    try {
      const planResult = await getInstallerPlan();
      if (requestId !== previewRequest || planContainer.hidden || !planContainer.isConnected) return;
      renderPlanPreview(planContainer, planResult, closeAllModals);
      focusModal(planContainer, btnPreview);
    } catch (err) {
      if (requestId !== previewRequest || planContainer.hidden || !planContainer.isConnected) return;
      planContainer.innerHTML = `
        <div class="plan-modal-overlay">
          <div class="plan-modal-card">
            <div class="plan-modal-header">
              <h3 class="plan-modal-title">Deployment Plan Error</h3>
              <button type="button" class="btn btn-close-plan" title="Close">✕</button>
            </div>
            <div class="plan-modal-body">
              <div class="notice error">${escapeHtml(err.message)}</div>
            </div>
            <div class="plan-modal-footer">
              <button type="button" class="btn btn-close-plan">Close</button>
            </div>
          </div>
        </div>
      `;
      planContainer.querySelectorAll(".btn-close-plan").forEach((btn) => {
        btn.addEventListener("click", closeAllModals);
      });
      focusModal(planContainer, btnPreview);
      const errOverlay = planContainer.querySelector(".plan-modal-overlay");
      errOverlay?.addEventListener("click", (e) => {
        if (e.target === errOverlay) {
          closeAllModals();
        }
      });
    } finally {
      if (requestId === previewRequest) checkDirtyState();
    }
  }
  btnPreview.addEventListener("click", previewDeploymentPlan);
}

function renderPlanPreview(container, plan, onClose) {
  const cfn = plan.cloudformation;
  const cc = plan.codecommit;
  const workspace = String(plan.workspaceDir || "");
  const quotedWorkspace = "'" + workspace.replaceAll("'", "'\\''") + "'";
  const deployCommand = `cd ${quotedWorkspace} && lza installer deploy`;
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
              <span class="badge badge-${cfn.operation === "NO_CHANGE" ? "success" : "warning"}">${escapeHtml(cfn.operation === "NO_CHANGE" ? "No deployment changes" : cfn.operation)}</span>
            </div>
            <p class="section-subtitle" style="margin-top: 0.25rem;">Read-only preview of CloudFormation and repository actions.</p>
          </div>
          <button type="button" class="btn btn-close-plan" title="Close Preview">✕</button>
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
              <span>${escapeHtml(!cc.status || cc.status === "N/A" ? "Not applicable" : cc.status)}</span>
            </div>
          </div>

          <h4 style="margin: 1.25rem 0 0.5rem 0; font-size: 0.875rem; font-weight: 600;">CloudFormation Parameter Changes (${diffEntries.length})</h4>
          ${diffTableHtml}

          ${ghWarning}

          <div class="notice info" style="margin-top: 1.25rem; display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;">
            <div>
              <strong>Deploy from your terminal</strong><br>
              <code>${escapeHtml(deployCommand)}</code>
            </div>
            <button type="button" id="btn-copy-deploy-cmd" class="btn btn-secondary btn-sm" style="white-space: nowrap;">
              <span>Copy Command</span>
            </button>
          </div>
        </div>
        <div class="plan-modal-footer">
          <button type="button" class="btn btn-close-plan">Close Preview</button>
        </div>
      </div>
    </div>
  `;

  const copyBtn = container.querySelector("#btn-copy-deploy-cmd");
  copyBtn?.addEventListener("click", () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(deployCommand);
      const span = copyBtn.querySelector("span");
      if (span) {
        const orig = span.textContent;
        span.textContent = "Copied!";
        setTimeout(() => {
          span.textContent = orig;
        }, 2000);
      }
    }
  });

  const closeHandler = typeof onClose === "function" ? onClose : () => {
    container.hidden = true;
    container.innerHTML = "";
  };

  const overlay = container.querySelector(".plan-modal-overlay");
  overlay?.addEventListener("click", (e) => {
    if (e.target === overlay) {
      closeHandler();
    }
  });

  container.querySelectorAll(".btn-close-plan").forEach((btn) => {
    btn.addEventListener("click", closeHandler);
  });
}
