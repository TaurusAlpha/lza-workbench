import {
  applyUninstall,
  getUninstallPlan,
  getUninstallProgress,
  resetUninstallProgress,
} from "./api.js";
import { escapeHtml, renderBadge } from "./overview.js";

// ==========================================
// State Management for Uninstall View
// ==========================================
let currentPlan = null;
let currentProgress = null;
let currentOptions = {
  assume_role_name: "AWSAccelerator-PipelineRole",
  region_mode: "CONFIGURED",
  custom_regions: "",
  account_mode: "ALL",
  custom_accounts: "",
  profiles_file: "",
  skip_installer: false,
  skip_pipeline: false,
};
let pollingTimer = null;
let pollingIntervalSeconds = 5; // Default 5 seconds per user request
let selectedBuckets = new Set();
let selectedRetainedIds = new Set();
let retainedTypeFilter = "ALL";
let isApplying = false;

export function cleanupUninstallPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

// ==========================================
// Main View Renderer
// ==========================================
export async function renderUninstall(container, options = {}) {
  cleanupUninstallPolling();

  try {
    const progressResp = await getUninstallProgress().catch(() => null);
    // ONLY divert to live progress if a background uninstallation thread is ACTUALLY running!
    if (progressResp && progressResp.isRunning) {
      renderLiveProgressView(container, progressResp);
      return;
    }
  } catch (_) {}

  // If a plan was already discovered and user didn't request options, show preview
  if (currentPlan && !options.showOptions) {
    renderPlanPreview(container);
    return;
  }

  // Otherwise, present Phase 0: Scope & Options form
  renderOptionsForm(container);
}

// ==========================================
// Phase 0: Scope & Options Configuration View
// ==========================================
function renderOptionsForm(container) {
  cleanupUninstallPolling();

  container.innerHTML = `
    <!-- Top Warning Banner -->
    <div class="alert alert-warning uninstall-danger-banner">
      <div class="alert-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </div>
      <div class="alert-content">
        <h3 class="alert-title">Destructive Solution Decommission</h3>
        <p class="alert-desc">
          Configure discovery scope and target parameters before querying AWS.
          You will review all discovered CloudFormation stacks, S3 buckets, and retained resources before uninstallation can proceed.
        </p>
      </div>
    </div>

    <article class="card card-full" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title-group">
          <h2 class="card-title">Discovery Scope &amp; Target Parameters</h2>
          <span class="card-subtitle">Specify which AWS accounts, regions, and roles should be targeted for teardown</span>
        </div>
      </div>
      <div class="card-body">
        <form id="uninstall-options-form">
          <!-- Role to assume -->
          <div class="form-group" style="margin-bottom: 1.25rem;">
            <label for="opt-assume-role" style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Execution / Assumed Role Name</label>
            <input
              type="text"
              id="opt-assume-role"
              class="form-input"
              value="${escapeHtml(currentOptions.assume_role_name || "AWSAccelerator-PipelineRole")}"
              placeholder="AWSAccelerator-PipelineRole"
            />
            <span class="field-hint" style="display: block; font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">
              Role assumed in target member accounts to query and delete CloudFormation stacks and resources.
            </span>
          </div>

          <!-- Regions Section -->
          <div class="form-group" style="margin-bottom: 1.25rem;">
            <label style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Target AWS Regions</label>
            <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.35rem;">
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="radio" name="opt-region-mode" value="CONFIGURED" ${currentOptions.region_mode === "CONFIGURED" ? "checked" : ""}>
                <span><strong>Configured Regions</strong> (default: discover from <code>global-config.yaml</code> or workspace default)</span>
              </label>
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="radio" name="opt-region-mode" value="ALL" ${currentOptions.region_mode === "ALL" ? "checked" : ""}>
                <span><strong>All Enabled Regions</strong> (<code>--all-regions</code>: query all enabled EC2 regions)</span>
              </label>
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="radio" name="opt-region-mode" value="CUSTOM" ${currentOptions.region_mode === "CUSTOM" ? "checked" : ""}>
                <span><strong>Specific Regions</strong> (comma-separated list)</span>
              </label>
            </div>
            <div id="wrapper-custom-regions" style="margin-top: 0.5rem; margin-left: 1.5rem; ${currentOptions.region_mode === "CUSTOM" ? "" : "display: none;"}">
              <input
                type="text"
                id="opt-custom-regions"
                class="form-input"
                placeholder="e.g. eu-west-1, us-east-1"
                value="${escapeHtml(currentOptions.custom_regions || "")}"
              />
            </div>
          </div>

          <!-- Accounts Section -->
          <div class="form-group" style="margin-bottom: 1.25rem;">
            <label style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Target AWS Accounts</label>
            <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.35rem;">
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="radio" name="opt-account-mode" value="ALL" ${currentOptions.account_mode === "ALL" ? "checked" : ""}>
                <span><strong>All Organization Accounts</strong> (auto-discover active accounts via AWS Organizations)</span>
              </label>
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="radio" name="opt-account-mode" value="MANAGEMENT" ${currentOptions.account_mode === "MANAGEMENT" ? "checked" : ""}>
                <span><strong>Management Account Only</strong> (scope teardown strictly to current management account)</span>
              </label>
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="radio" name="opt-account-mode" value="CUSTOM" ${currentOptions.account_mode === "CUSTOM" ? "checked" : ""}>
                <span><strong>Specific Accounts</strong> (comma-separated Account IDs)</span>
              </label>
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="radio" name="opt-account-mode" value="PROFILES" ${currentOptions.account_mode === "PROFILES" ? "checked" : ""}>
                <span><strong>Profiles Mapping File</strong> (load account/profile mappings from a YAML or JSON file)</span>
              </label>
            </div>
            <div id="wrapper-custom-accounts" style="margin-top: 0.5rem; margin-left: 1.5rem; ${currentOptions.account_mode === "CUSTOM" ? "" : "display: none;"}">
              <input
                type="text"
                id="opt-custom-accounts"
                class="form-input"
                placeholder="e.g. 111111111111, 222222222222"
                value="${escapeHtml(currentOptions.custom_accounts || "")}"
              />
            </div>
            <div id="wrapper-profiles-file" style="margin-top: 0.5rem; margin-left: 1.5rem; ${currentOptions.account_mode === "PROFILES" ? "" : "display: none;"}">
              <input
                type="text"
                id="opt-profiles-file"
                class="form-input"
                placeholder="path/to/profiles.yaml"
                value="${escapeHtml(currentOptions.profiles_file || "")}"
              />
            </div>
          </div>

          <!-- Foundation Stacks Section -->
          <div class="form-group" style="margin-bottom: 1.25rem;">
            <label style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Foundation Stacks Protection</label>
            <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.35rem;">
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="checkbox" id="opt-skip-installer" ${currentOptions.skip_installer ? "checked" : ""}>
                <span><strong>Skip Installer Stack</strong> (preserve <code>AWSAccelerator-InstallerStack</code> and CDK toolkit)</span>
              </label>
              <label class="checkbox-label" style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="checkbox" id="opt-skip-pipeline" ${currentOptions.skip_pipeline ? "checked" : ""}>
                <span><strong>Skip Pipeline Stack</strong> (preserve <code>AWSAccelerator-PipelineStack</code> and CodePipeline)</span>
              </label>
            </div>
          </div>

          <div class="form-actions" style="display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border-card);">
            <a href="#/overview" class="btn btn-ghost">Cancel</a>
            <button type="submit" class="btn btn-primary" id="btn-submit-scan">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              Scan Resources &amp; Preview Plan &rarr;
            </button>
          </div>
        </form>
      </div>
    </article>
  `;

  // Bind dynamic visibility for radio options
  const regionRadios = container.querySelectorAll("input[name='opt-region-mode']");
  const wrapperCustomRegions = container.querySelector("#wrapper-custom-regions");
  regionRadios.forEach((r) => {
    r.addEventListener("change", () => {
      if (wrapperCustomRegions) {
        wrapperCustomRegions.style.display = r.value === "CUSTOM" && r.checked ? "" : "none";
      }
    });
  });

  const accountRadios = container.querySelectorAll("input[name='opt-account-mode']");
  const wrapperCustomAccounts = container.querySelector("#wrapper-custom-accounts");
  const wrapperProfilesFile = container.querySelector("#wrapper-profiles-file");
  accountRadios.forEach((r) => {
    r.addEventListener("change", () => {
      if (wrapperCustomAccounts) {
        wrapperCustomAccounts.style.display = r.value === "CUSTOM" && r.checked ? "" : "none";
      }
      if (wrapperProfilesFile) {
        wrapperProfilesFile.style.display = r.value === "PROFILES" && r.checked ? "" : "none";
      }
    });
  });

  const form = container.querySelector("#uninstall-options-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const selRegionRadio = container.querySelector("input[name='opt-region-mode']:checked");
    const selAccountRadio = container.querySelector("input[name='opt-account-mode']:checked");
    const customRegionsVal = container.querySelector("#opt-custom-regions")?.value.trim() || "";
    const customAccountsVal = container.querySelector("#opt-custom-accounts")?.value.trim() || "";
    const profilesFileVal = container.querySelector("#opt-profiles-file")?.value.trim() || "";
    const assumeRoleVal = container.querySelector("#opt-assume-role")?.value.trim() || "AWSAccelerator-PipelineRole";
    const skipInstallerVal = container.querySelector("#opt-skip-installer")?.checked || false;
    const skipPipelineVal = container.querySelector("#opt-skip-pipeline")?.checked || false;

    currentOptions = {
      assume_role_name: assumeRoleVal,
      region_mode: selRegionRadio?.value || "CONFIGURED",
      custom_regions: customRegionsVal,
      account_mode: selAccountRadio?.value || "ALL",
      custom_accounts: customAccountsVal,
      profiles_file: profilesFileVal,
      skip_installer: skipInstallerVal,
      skip_pipeline: skipPipelineVal,
    };

    const planPayload = {
      assume_role_name: currentOptions.assume_role_name,
      skip_installer: currentOptions.skip_installer,
      skip_pipeline: currentOptions.skip_pipeline,
      all_regions: currentOptions.region_mode === "ALL",
      regions: currentOptions.region_mode === "CUSTOM"
        ? currentOptions.custom_regions.split(",").map((r) => r.trim()).filter(Boolean)
        : [],
      accounts: currentOptions.account_mode === "CUSTOM"
        ? currentOptions.custom_accounts.split(",").map((a) => a.trim()).filter(Boolean)
        : [],
      profiles_file: currentOptions.account_mode === "PROFILES"
        ? (currentOptions.profiles_file || null)
        : null,
    };

    container.innerHTML = `
      <div class="view-loading">
        <div class="spinner"></div>
        <p>Discovering LZA resources across accounts and regions...</p>
        <span class="text-muted" style="font-size: 0.8125rem; margin-top: 0.5rem;">
          Querying CloudFormation stacks, S3 buckets, and retained resources based on selected scope...
        </span>
      </div>
    `;

    try {
      const planResp = await getUninstallPlan(planPayload);
      currentPlan = planResp.plan;
      selectedBuckets.clear();
      selectedRetainedIds = new Set(currentPlan.retainedResources.map((r) => r.physicalId));
      renderPlanPreview(container);
    } catch (error) {
      container.innerHTML = `
        <div class="card card-full">
          <div class="card-header">
            <h2 class="card-title">Discovery Error</h2>
          </div>
          <div class="card-body">
            <div class="alert alert-danger">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <span>${escapeHtml(error.message || "Failed to discover LZA resources.")}</span>
            </div>
            <div style="margin-top: 1.25rem; display: flex; gap: 0.75rem;">
              <button type="button" class="btn btn-outline" id="btn-err-back-options">&larr; Adjust Scope &amp; Options</button>
              <button type="button" class="btn btn-primary" id="btn-err-retry">Retry Discovery</button>
            </div>
          </div>
        </div>
      `;
      container.querySelector("#btn-err-back-options")?.addEventListener("click", () => renderOptionsForm(container));
      container.querySelector("#btn-err-retry")?.addEventListener("click", () => {
        form.dispatchEvent(new Event("submit"));
      });
    }
  });
}

// ==========================================
// Phase 1: Plan & Resource Selection View
// ==========================================
function renderPlanPreview(container) {
  if (!currentPlan) return;

  const {
    customerName,
    customerSlug,
    totalStacks,
    protectedStacks,
    totalS3Buckets,
    totalRetainedResources,
    accounts,
    regions,
    stacks,
    s3Buckets,
    retainedResources,
  } = currentPlan;

  // Group retained resources by resource type
  const typeCounts = {};
  for (const r of retainedResources) {
    typeCounts[r.resourceType] = (typeCounts[r.resourceType] || 0) + 1;
  }
  const availableTypes = Object.keys(typeCounts).sort();

  const filteredRetained =
    retainedTypeFilter === "ALL"
      ? retainedResources
      : retainedResources.filter((r) => r.resourceType === retainedTypeFilter);

  container.innerHTML = `
    <!-- Options Header / Breadcrumb Bar -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem;">
      <button type="button" class="btn btn-outline" id="btn-back-to-options">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        Adjust Scope &amp; Options
      </button>
      <div style="display: flex; align-items: center; gap: 0.5rem;">
        <span class="text-muted" style="font-size: 0.8125rem;">Assumed Role:</span>
        <span class="badge badge-neutral mono-val">${escapeHtml(currentOptions.assume_role_name || "AWSAccelerator-PipelineRole")}</span>
      </div>
    </div>

    <!-- Top Warning Banner -->
    <div class="alert alert-warning uninstall-danger-banner">
      <div class="alert-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </div>
      <div class="alert-content">
        <h3 class="alert-title">Destructive Solution Decommission</h3>
        <p class="alert-desc">
          You are preparing to delete the Landing Zone Accelerator deployment for 
          <strong>${escapeHtml(customerName)}</strong> (<code>${escapeHtml(customerSlug)}</code>).
          Stacks will be removed in reverse dependency order. Termination protection will be disabled automatically on protected stacks.
        </p>
      </div>
    </div>

    <!-- Summary Metrics Cards Grid -->
    <div class="card-grid" style="margin-bottom: 1.5rem;">
      <div class="card metric-card">
        <span class="metric-label">Discovered Stacks</span>
        <strong class="metric-value">${totalStacks}</strong>
        <span class="metric-subtext">${protectedStacks > 0 ? `<span class="badge badge-danger">${protectedStacks} protected</span>` : '<span class="badge badge-success">0 protected</span>'}</span>
      </div>

      <div class="card metric-card">
        <span class="metric-label">Target Accounts</span>
        <strong class="metric-value">${accounts.length}</strong>
        <span class="metric-subtext mono-val">${escapeHtml(accounts.map((a) => a.name).join(", "))}</span>
      </div>

      <div class="card metric-card">
        <span class="metric-label">LZA S3 Buckets</span>
        <strong class="metric-value">${totalS3Buckets}</strong>
        <span class="metric-subtext">${selectedBuckets.size} selected for cleanup</span>
      </div>

      <div class="card metric-card">
        <span class="metric-label">Retained Resources</span>
        <strong class="metric-value">${totalRetainedResources}</strong>
        <span class="metric-subtext">${selectedRetainedIds.size} selected for cleanup</span>
      </div>
    </div>

    <!-- Main Content Tabs / Accordions -->
    <div class="uninstall-sections">
      <!-- 1. Stacks Table Card -->
      <article class="card card-full" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-group">
            <h2 class="card-title">CloudFormation Stacks (${totalStacks})</h2>
            <span class="card-subtitle">Ordered in dependency-safe reverse deployment sequence</span>
          </div>
          <div class="card-header-actions">
            <span class="badge badge-neutral">${escapeHtml(regions.join(", "))}</span>
          </div>
        </div>
        <div class="card-body no-padding table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 40px;">#</th>
                <th>Stack Name</th>
                <th>Account</th>
                <th>Region</th>
                <th>Termination Protection</th>
                <th style="text-align: right;">Retained Items</th>
              </tr>
            </thead>
            <tbody>
              ${
                stacks.length === 0
                  ? '<tr><td colspan="6" class="text-center text-muted">No deployed LZA CloudFormation stacks discovered.</td></tr>'
                  : stacks
                      .map(
                        (s, idx) => `
                    <tr>
                      <td class="text-muted">${idx + 1}</td>
                      <td>
                        <strong class="mono-val">${escapeHtml(s.stackName)}</strong>
                        ${s.isPipelineOrInstaller ? '<span class="badge badge-purple" style="margin-left: 6px;">Foundation</span>' : ""}
                      </td>
                      <td><span class="mono-val">${escapeHtml(s.accountName)}</span> <span class="text-muted">(${escapeHtml(s.accountId)})</span></td>
                      <td><span class="mono-val">${escapeHtml(s.region)}</span></td>
                      <td>
                        ${
                          s.terminationProtection
                            ? '<span class="badge badge-danger">PROTECTED</span>'
                            : '<span class="badge badge-neutral">Disabled</span>'
                        }
                      </td>
                      <td style="text-align: right;">
                        ${s.retainedResources.length > 0 ? `<span class="badge badge-warning">${s.retainedResources.length}</span>` : '<span class="text-muted">—</span>'}
                      </td>
                    </tr>
                  `
                      )
                      .join("")
              }
            </tbody>
          </table>
        </div>
      </article>

      <!-- 2. S3 Buckets Cleanup Card -->
      <article class="card card-full" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-group">
            <h2 class="card-title">LZA S3 Buckets (${totalS3Buckets})</h2>
            <span class="card-subtitle">Select buckets to empty and delete permanently</span>
          </div>
          <div class="card-header-actions">
            <button type="button" class="btn btn-sm btn-ghost" id="btn-toggle-all-buckets">
              ${selectedBuckets.size === totalS3Buckets && totalS3Buckets > 0 ? "Deselect All" : "Select All"}
            </button>
          </div>
        </div>
        <div class="card-body no-padding table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 40px; text-align: center;">
                  <input type="checkbox" id="chk-buckets-header" ${selectedBuckets.size === totalS3Buckets && totalS3Buckets > 0 ? "checked" : ""}>
                </th>
                <th>Bucket Name</th>
                <th>Account</th>
                <th>Region</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${
                s3Buckets.length === 0
                  ? '<tr><td colspan="5" class="text-center text-muted">No LZA S3 buckets discovered.</td></tr>'
                  : s3Buckets
                      .map(
                        (b) => `
                    <tr class="${selectedBuckets.has(b.bucketName) ? "row-selected" : ""}">
                      <td style="text-align: center;">
                        <input type="checkbox" class="chk-bucket" data-bucket="${escapeHtml(b.bucketName)}" ${selectedBuckets.has(b.bucketName) ? "checked" : ""}>
                      </td>
                      <td><strong class="mono-val">${escapeHtml(b.bucketName)}</strong></td>
                      <td><span class="mono-val">${escapeHtml(b.accountId)}</span></td>
                      <td><span class="mono-val">${escapeHtml(b.region)}</span></td>
                      <td>
                        ${
                          selectedBuckets.has(b.bucketName)
                            ? '<span class="badge badge-danger">EMPTY &amp; DELETE</span>'
                            : '<span class="badge badge-success">RETAIN (Preserved)</span>'
                        }
                      </td>
                    </tr>
                  `
                      )
                      .join("")
              }
            </tbody>
          </table>
        </div>
      </article>

      <!-- 3. Retained Resources Selection Card -->
      <article class="card card-full" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-group">
            <h2 class="card-title">Retained Resources (${totalRetainedResources})</h2>
            <span class="card-subtitle">Granular selection of resources preserved by AWS CloudFormation DeletionPolicy: Retain</span>
          </div>
          <div class="card-header-actions">
            <!-- Filter by resource type -->
            <select class="input-select" id="select-retained-type" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;">
              <option value="ALL" ${retainedTypeFilter === "ALL" ? "selected" : ""}>All Types (${totalRetainedResources})</option>
              ${availableTypes.map((t) => `<option value="${escapeHtml(t)}" ${retainedTypeFilter === t ? "selected" : ""}>${escapeHtml(t)} (${typeCounts[t]})</option>`).join("")}
            </select>
            <button type="button" class="btn btn-sm btn-ghost" id="btn-toggle-all-retained">
              ${selectedRetainedIds.size === totalRetainedResources && totalRetainedResources > 0 ? "Deselect All" : "Select All"}
            </button>
          </div>
        </div>
        <div class="card-body no-padding table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 40px; text-align: center;">
                  <input type="checkbox" id="chk-retained-header" ${selectedRetainedIds.size === filteredRetained.length && filteredRetained.length > 0 ? "checked" : ""}>
                </th>
                <th>Resource Type</th>
                <th>Physical ID</th>
                <th>Account</th>
                <th>Region</th>
                <th>Policy Action</th>
              </tr>
            </thead>
            <tbody>
              ${
                filteredRetained.length === 0
                  ? '<tr><td colspan="6" class="text-center text-muted">No retained resources matching selection.</td></tr>'
                  : filteredRetained
                      .map(
                        (r) => `
                    <tr class="${selectedRetainedIds.has(r.physicalId) ? "row-selected" : ""}">
                      <td style="text-align: center;">
                        <input type="checkbox" class="chk-retained" data-id="${escapeHtml(r.physicalId)}" ${selectedRetainedIds.has(r.physicalId) ? "checked" : ""}>
                      </td>
                      <td><span class="badge badge-neutral">${escapeHtml(r.resourceType)}</span></td>
                      <td><strong class="mono-val truncate" title="${escapeHtml(r.physicalId)}">${escapeHtml(r.physicalId)}</strong></td>
                      <td><span class="mono-val">${escapeHtml(r.accountId)}</span></td>
                      <td><span class="mono-val">${escapeHtml(r.region)}</span></td>
                      <td>
                        ${
                          selectedRetainedIds.has(r.physicalId)
                            ? '<span class="badge badge-danger">FORCE DELETE</span>'
                            : '<span class="badge badge-success">RETAIN (Preserved)</span>'
                        }
                      </td>
                    </tr>
                  `
                      )
                      .join("")
              }
            </tbody>
          </table>
        </div>
      </article>

      <!-- Action Footer -->
      <div class="card card-full" style="display: flex; flex-direction: row; align-items: center; justify-content: space-between; padding: 1.25rem;">
        <div>
          <span class="text-muted">Review all resources before proceeding. Teardown cannot be undone.</span>
        </div>
        <div style="display: flex; gap: 0.75rem;">
          <a href="#/overview" class="btn btn-ghost">Cancel</a>
          <button type="button" class="btn btn-danger" id="btn-proceed-uninstall" ${totalStacks === 0 && selectedBuckets.size === 0 && selectedRetainedIds.size === 0 ? "disabled" : ""}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            Proceed to Uninstallation...
          </button>
        </div>
      </div>
    </div>
  `;

  // Attach event handlers
  setupPlanEvents(container);
}

function setupPlanEvents(container) {
  // Back to Scope & Options
  const btnBackToOptions = container.querySelector("#btn-back-to-options");
  if (btnBackToOptions) {
    btnBackToOptions.addEventListener("click", () => {
      renderOptionsForm(container);
    });
  }

  // S3 Buckets Select All / Header Checkbox
  const chkBucketsHeader = container.querySelector("#chk-buckets-header");
  const btnToggleAllBuckets = container.querySelector("#btn-toggle-all-buckets");

  function toggleAllBuckets() {
    if (selectedBuckets.size === currentPlan.s3Buckets.length) {
      selectedBuckets.clear();
    } else {
      selectedBuckets = new Set(currentPlan.s3Buckets.map((b) => b.bucketName));
    }
    renderPlanPreview(container);
  }

  if (chkBucketsHeader) chkBucketsHeader.addEventListener("change", toggleAllBuckets);
  if (btnToggleAllBuckets) btnToggleAllBuckets.addEventListener("click", toggleAllBuckets);

  // Individual Bucket Checkboxes
  container.querySelectorAll(".chk-bucket").forEach((chk) => {
    chk.addEventListener("change", (e) => {
      const name = e.target.getAttribute("data-bucket");
      if (e.target.checked) {
        selectedBuckets.add(name);
      } else {
        selectedBuckets.delete(name);
      }
      renderPlanPreview(container);
    });
  });

  // Retained Resources Type Filter
  const selectRetainedType = container.querySelector("#select-retained-type");
  if (selectRetainedType) {
    selectRetainedType.addEventListener("change", (e) => {
      retainedTypeFilter = e.target.value;
      renderPlanPreview(container);
    });
  }

  // Retained Resources Toggle All
  const chkRetainedHeader = container.querySelector("#chk-retained-header");
  const btnToggleAllRetained = container.querySelector("#btn-toggle-all-retained");

  function toggleAllRetained() {
    if (selectedRetainedIds.size === currentPlan.retainedResources.length) {
      selectedRetainedIds.clear();
    } else {
      selectedRetainedIds = new Set(currentPlan.retainedResources.map((r) => r.physicalId));
    }
    renderPlanPreview(container);
  }

  if (chkRetainedHeader) chkRetainedHeader.addEventListener("change", toggleAllRetained);
  if (btnToggleAllRetained) btnToggleAllRetained.addEventListener("click", toggleAllRetained);

  // Individual Retained Checkboxes
  container.querySelectorAll(".chk-retained").forEach((chk) => {
    chk.addEventListener("change", (e) => {
      const id = e.target.getAttribute("data-id");
      if (e.target.checked) {
        selectedRetainedIds.add(id);
      } else {
        selectedRetainedIds.delete(id);
      }
      renderPlanPreview(container);
    });
  });

  // Open Confirmation Modal
  const btnProceed = container.querySelector("#btn-proceed-uninstall");
  if (btnProceed) {
    btnProceed.addEventListener("click", () => {
      openConfirmationModal(container);
    });
  }
}

// ==========================================
// Phase 2: Confirmation Modal
// ==========================================
function openConfirmationModal(container) {
  if (!currentPlan) return;

  const { customerName, customerSlug, totalStacks, protectedStacks } = currentPlan;
  const bucketCount = selectedBuckets.size;
  const retainedCount = selectedRetainedIds.size;

  const modalOverlay = document.createElement("div");
  modalOverlay.className = "plan-modal-overlay";
  modalOverlay.innerHTML = `
    <div class="plan-modal-card" style="border-top: 4px solid var(--danger);">
      <div class="plan-modal-header">
        <div>
          <h3 class="plan-modal-title" style="color: var(--danger); display: flex; align-items: center; gap: 8px;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            Confirm Permanent Teardown
          </h3>
          <span class="plan-modal-subtitle">Destructive action for customer: <strong>${escapeHtml(customerName)}</strong></span>
        </div>
        <button type="button" class="btn-close-modal" id="modal-close-btn">&times;</button>
      </div>

      <div class="plan-modal-body">
        <p style="margin-bottom: 1rem;">
          You are about to permanently delete the following AWS infrastructure:
        </p>
        <ul style="margin-bottom: 1.25rem; padding-left: 1.25rem; color: var(--text-primary); line-height: 1.6;">
          <li><strong>${totalStacks} CloudFormation Stacks</strong> (${protectedStacks} with termination protection will be unlocked)</li>
          <li><strong>${bucketCount} S3 Buckets</strong> will be completely emptied and deleted</li>
          <li><strong>${retainedCount} Retained Resources</strong> will be force-deleted (LogGroups, KMS keys, etc.)</li>
        </ul>

        <div class="alert alert-danger" style="margin-bottom: 1.25rem;">
          <span>This action cannot be undone. All configuration and operational metadata for this workspace will be reset.</span>
        </div>

        <div class="form-group">
          <label class="form-label" for="slug-confirm-input">
            To proceed, type the customer slug <strong class="mono-val" style="color: var(--warning);">${escapeHtml(customerSlug)}</strong> below:
          </label>
          <input type="text" class="input-text" id="slug-confirm-input" placeholder="${escapeHtml(customerSlug)}" autocomplete="off">
        </div>
      </div>

      <div class="plan-modal-footer">
        <button type="button" class="btn btn-ghost" id="modal-cancel-btn">Cancel</button>
        <button type="button" class="btn btn-danger" id="modal-confirm-btn" disabled>
          Confirm &amp; Execute Teardown
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modalOverlay);

  const closeBtn = modalOverlay.querySelector("#modal-close-btn");
  const cancelBtn = modalOverlay.querySelector("#modal-cancel-btn");
  const confirmBtn = modalOverlay.querySelector("#modal-confirm-btn");
  const input = modalOverlay.querySelector("#slug-confirm-input");

  const closeModal = () => modalOverlay.remove();
  closeBtn.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);

  input.addEventListener("input", () => {
    confirmBtn.disabled = input.value.trim() !== customerSlug;
  });

  confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Starting Teardown...";

    try {
      const payload = {
        customer_slug_confirmation: input.value.trim(),
        delete_s3_buckets: selectedBuckets.size > 0,
        selected_bucket_names: Array.from(selectedBuckets),
        delete_retained_resources: selectedRetainedIds.size > 0,
        selected_retained_ids: Array.from(selectedRetainedIds),
        regions: currentOptions.region_mode === "CUSTOM"
          ? currentOptions.custom_regions.split(",").map((r) => r.trim()).filter(Boolean)
          : [],
        all_regions: currentOptions.region_mode === "ALL",
        accounts: currentOptions.account_mode === "CUSTOM"
          ? currentOptions.custom_accounts.split(",").map((a) => a.trim()).filter(Boolean)
          : [],
        assume_role_name: currentOptions.assume_role_name || "AWSAccelerator-PipelineRole",
        profiles_file: currentOptions.account_mode === "PROFILES"
          ? (currentOptions.profiles_file || "").trim() || null
          : null,
        skip_installer: Boolean(currentOptions.skip_installer),
        skip_pipeline: Boolean(currentOptions.skip_pipeline),
      };

      await applyUninstall(payload);
      closeModal();
      // Transition immediately to Phase 3: Live Progress View
      renderLiveProgressView(container);
    } catch (error) {
      alert(`Failed to start uninstallation: ${error.message}`);
      confirmBtn.disabled = false;
      confirmBtn.textContent = "Confirm & Execute Teardown";
    }
  });

  input.focus();
}

// ==========================================
// Phase 3 & 4: Live Execution Monitor & Summary
// ==========================================
async function renderLiveProgressView(container, initialProgress = null) {
  cleanupUninstallPolling();

  container.innerHTML = `
    <article class="card card-full" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title-group">
          <h2 class="card-title" id="progress-card-title">Teardown Execution in Progress</h2>
          <span class="card-subtitle" id="progress-card-subtitle">Monitoring active uninstallation progress...</span>
        </div>
        <div class="card-header-actions" style="display: flex; align-items: center; gap: 0.75rem;">
          <button type="button" class="btn btn-sm btn-outline" id="btn-exit-progress" title="Return to Scope &amp; Options">
            &larr; Scope &amp; Options
          </button>
          <!-- Polling interval selector (User request: default 5s, adjustable) -->
          <label for="select-poll-interval" style="font-size: 0.75rem; color: var(--text-muted);">Refresh Interval:</label>
          <select class="input-select" id="select-poll-interval" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;">
            <option value="2" ${pollingIntervalSeconds === 2 ? "selected" : ""}>2 seconds</option>
            <option value="5" ${pollingIntervalSeconds === 5 ? "selected" : ""}>5 seconds (Default)</option>
            <option value="10" ${pollingIntervalSeconds === 10 ? "selected" : ""}>10 seconds</option>
            <option value="15" ${pollingIntervalSeconds === 15 ? "selected" : ""}>15 seconds</option>
          </select>
          <span class="badge badge-warning" id="progress-status-badge">IN_PROGRESS</span>
        </div>
      </div>

      <div class="card-body">
        <!-- Progress Bar -->
        <div class="uninstall-progress-bar-container" style="margin-bottom: 1.5rem;">
          <div class="progress-bar-track" style="height: 8px; background: var(--bg-card-muted); border-radius: 4px; overflow: hidden;">
            <div class="progress-bar-fill" id="progress-bar-fill" style="height: 100%; width: 5%; background: var(--brand-primary); transition: width 300ms ease;"></div>
          </div>
          <div style="display: flex; justify-content: space-between; margin-top: 0.5rem; font-size: 0.8rem; color: var(--text-muted);">
            <span id="progress-stats-deleted">Deleted 0 stacks</span>
            <span id="progress-stats-percent">0%</span>
          </div>
        </div>

        <!-- Activity Feed / Event Log -->
        <div class="section-divider-label" style="margin-bottom: 0.75rem;">Execution Activity Stream</div>
        <div class="uninstall-event-stream" id="event-stream" style="max-height: 320px; overflow-y: auto; background: var(--bg-card-muted); border: 1px solid var(--border-card); border-radius: 6px; padding: 0.75rem; font-family: monospace; font-size: 0.8rem;">
          <div class="text-muted">Waiting for execution events...</div>
        </div>

        <!-- Final Summary Block (Hidden until complete) -->
        <div id="final-summary-block" style="display: none; margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border-card);">
          <div class="alert alert-success" id="final-status-alert">
            <h4 style="margin: 0 0 0.25rem 0;">Uninstallation Completed</h4>
            <p style="margin: 0;" id="final-status-desc">All selected resources have been successfully removed.</p>
          </div>
          <div style="margin-top: 1rem; display: flex; justify-content: flex-end; gap: 0.75rem;">
            <button type="button" class="btn btn-outline" id="btn-back-to-options-terminal">&larr; Scope &amp; Options</button>
            <a href="#/overview" class="btn btn-primary">Return to Overview</a>
          </div>
        </div>
      </div>
    </article>
  `;

  const exitToOptions = () => {
    cleanupUninstallPolling();
    currentPlan = null;
    renderOptionsForm(container);
  };
  container.querySelector("#btn-exit-progress")?.addEventListener("click", exitToOptions);
  container.querySelector("#btn-back-to-options-terminal")?.addEventListener("click", exitToOptions);

  const selectPoll = container.querySelector("#select-poll-interval");
  if (selectPoll) {
    selectPoll.addEventListener("change", (e) => {
      pollingIntervalSeconds = parseInt(e.target.value, 10) || 5;
      restartPolling();
    });
  }

  async function updateProgressUI() {
    try {
      const data = await getUninstallProgress();
      currentProgress = data;

      const title = container.querySelector("#progress-card-title");
      const badge = container.querySelector("#progress-status-badge");
      const fill = container.querySelector("#progress-bar-fill");
      const deletedStats = container.querySelector("#progress-stats-deleted");
      const percentStats = container.querySelector("#progress-stats-percent");
      const stream = container.querySelector("#event-stream");
      const summaryBlock = container.querySelector("#final-summary-block");
      const summaryAlert = container.querySelector("#final-status-alert");
      const summaryDesc = container.querySelector("#final-status-desc");

      const deletedCount = data.deletedStacks.length;
      const failedCount = data.failedStacks.length;
      const totalEstimated = currentPlan ? currentPlan.totalStacks : deletedCount || 1;
      const pct = Math.min(100, Math.round((deletedCount / Math.max(1, totalEstimated)) * 100));

      if (fill) fill.style.width = `${Math.max(5, pct)}%`;
      if (deletedStats) deletedStats.textContent = `Deleted ${deletedCount} of ${totalEstimated} stacks (${failedCount} failed)`;
      if (percentStats) percentStats.textContent = `${pct}%`;

      // Render activity feed
      const events = [];
      for (const s of data.deletedStacks) {
        events.push(`<div style="color: var(--success); margin-bottom: 4px;">✓ Successfully deleted stack ${escapeHtml(s)}</div>`);
      }
      for (const f of data.failedStacks) {
        events.push(`<div style="color: var(--danger); margin-bottom: 4px;">✗ Failed deleting stack ${escapeHtml(f.stack_name || f.stackName)}: ${escapeHtml(f.error)}</div>`);
      }
      for (const b of data.deletedBuckets) {
        events.push(`<div style="color: var(--success); margin-bottom: 4px;">✓ Emptied and deleted S3 bucket ${escapeHtml(b)}</div>`);
      }
      for (const r of data.deletedRetained) {
        events.push(`<div style="color: var(--brand-primary); margin-bottom: 4px;">✓ Deleted retained ${escapeHtml(r.resource_type || r.resourceType)} '${escapeHtml(r.physical_id || r.physicalId)}'</div>`);
      }

      if (stream && events.length > 0) {
        stream.innerHTML = events.join("");
        stream.scrollTop = stream.scrollHeight;
      }

      // Check if finished
      const isTerminal = data.status === "COMPLETED" || data.status === "FAILED" || !data.isRunning;
      if (isTerminal && data.status !== "IN_PROGRESS") {
        cleanupUninstallPolling();
        if (badge) {
          badge.className = data.status === "COMPLETED" ? "badge badge-success" : "badge badge-danger";
          badge.textContent = data.status;
        }
        if (title) title.textContent = data.status === "COMPLETED" ? "Uninstallation Completed" : "Uninstallation Finished with Failures";
        if (summaryBlock) summaryBlock.style.display = "block";
        if (summaryAlert) summaryAlert.className = data.status === "COMPLETED" ? "alert alert-success" : "alert alert-danger";
        if (summaryDesc) {
          summaryDesc.textContent = `Completed with ${deletedCount} deleted stacks, ${data.deletedBuckets.length} deleted buckets, and ${data.deletedRetained.length} deleted retained resources.`;
        }
      }
    } catch (e) {
      console.warn("Error polling uninstall progress:", e);
    }
  }

  function restartPolling() {
    cleanupUninstallPolling();
    pollingTimer = setInterval(updateProgressUI, pollingIntervalSeconds * 1000);
  }

  // Initial immediate run and start interval
  await updateProgressUI();
  restartPolling();
}

