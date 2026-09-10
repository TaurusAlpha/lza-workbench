import {
  applyWorkspaceImport,
  applyWorkspaceInit,
  discoverWorkspaceImport,
  openWorkspace,
  prepareWorkspaceImport,
  previewWorkspaceInit,
} from "./api.js";
import { escapeHtml } from "./overview.js";

export function renderSetup(container, activeWorkspace = null, onDone = null) {
  let activeTab = "create"; // "create" | "import" | "open"
  let createPreviewData = null;
  let importPreviewData = null;

  function setNotice(message, type = "info") {
    const noticeEl = container.querySelector(".setup-notice");
    if (!noticeEl) return;
    if (!message) {
      noticeEl.textContent = "";
      noticeEl.className = "setup-notice";
      noticeEl.hidden = true;
    } else {
      noticeEl.textContent = message;
      noticeEl.className = `setup-notice notice ${type}`;
      noticeEl.hidden = false;
    }
  }

  function render() {
    const hasActive = activeWorkspace && activeWorkspace.hasWorkspace;
    const currentPath = hasActive ? activeWorkspace.workspaceDir : "";

    container.innerHTML = `
      <div class="setup-container">
        <header class="setup-header">
          <div class="setup-tabs-bar" role="tablist" aria-label="Workspace Setup Options">
            <button type="button" role="tab" class="tab-btn ${activeTab === "create" ? "active" : ""}" data-tab="create" id="tab-create">
              Create New Workspace
            </button>
            <button type="button" role="tab" class="tab-btn ${activeTab === "import" ? "active" : ""}" data-tab="import" id="tab-import">
              Import Existing Workspace
            </button>
            <button type="button" role="tab" class="tab-btn ${activeTab === "open" ? "active" : ""}" data-tab="open" id="tab-open">
              Open Existing Workspace
            </button>
          </div>
        </header>

        <div class="setup-notice notice" hidden></div>

        <div class="setup-tab-content">
          ${activeTab === "create" ? renderCreateTab() : ""}
          ${activeTab === "import" ? renderImportTab() : ""}
          ${activeTab === "open" ? renderOpenTab(currentPath) : ""}
        </div>
      </div>
    `;

    bindTabEvents();
    if (activeTab === "create") bindCreateEvents();
    if (activeTab === "import") bindImportEvents();
    if (activeTab === "open") bindOpenEvents();
  }

  function renderCreateTab() {
    return `
      <div class="setup-panel card" id="create-panel">
        <div class="panel-intro">
          <h2 class="section-heading">Create New Workspace</h2>
          <p class="section-desc">Initialize a new local LZA customer workspace with declarative configuration metadata.</p>
        </div>

        <form id="create-form" class="setup-form" onsubmit="return false;">
          <div class="form-group">
            <label for="create-customer-name">Customer Name <span class="required">*</span></label>
            <input type="text" id="create-customer-name" class="form-input" placeholder="e.g. Acme Corp" required />
            <span class="field-hint">Used to derive resource names, customer slug, and directories.</span>
          </div>

          <div class="form-group">
            <label for="create-workspace-dir">Workspace Directory</label>
            <input type="text" id="create-workspace-dir" class="form-input" placeholder="Leave blank for automatic directory name" />
            <span class="field-hint">Optional path where the workspace directory will be created.</span>
          </div>

          <div class="form-row">
            <div class="form-group flex-1">
              <label for="create-aws-region">AWS Region <span class="required">*</span></label>
              <input type="text" id="create-aws-region" class="form-input" value="us-east-1" required />
            </div>
            <div class="form-group flex-1">
              <label for="create-aws-profile">AWS Profile</label>
              <input type="text" id="create-aws-profile" class="form-input" placeholder="Auto: &lt;customer-slug&gt;-root" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group flex-1">
              <label for="create-lza-version">LZA Version <span class="required">*</span></label>
              <input type="text" id="create-lza-version" class="form-input" value="v1.15.5" required />
            </div>
            <div class="form-group flex-1 checkbox-field">
              <label class="checkbox-label">
                <input type="checkbox" id="create-force" />
                <span>Overwrite existing directory files</span>
              </label>
            </div>
          </div>

          <div class="form-actions">
            <button type="button" id="create-preview-btn" class="btn btn-primary">Preview &amp; Validate</button>
          </div>
        </form>

        <div id="create-preview-area" ${createPreviewData ? "" : "hidden"}>
          ${createPreviewData ? renderCreatePreview(createPreviewData) : ""}
        </div>
      </div>
    `;
  }

  function renderCreatePreview(data) {
    const planned = data.plannedPaths || [];
    return `
      <div class="preview-card">
        <h3 class="preview-title">Initialization Preview</h3>
        <div class="kv-grid">
          <div class="kv-row">
            <dt class="kv-label">Resolved Directory</dt>
            <dd class="kv-value mono-val">${escapeHtml(data.workspaceDir)}</dd>
          </div>
          <div class="kv-row">
            <dt class="kv-label">Customer Slug</dt>
            <dd class="kv-value mono-val">${escapeHtml(data.customerSlug)}</dd>
          </div>
          <div class="kv-row">
            <dt class="kv-label">Directory Status</dt>
            <dd class="kv-value">${data.existingDirectory ? '<span class="badge badge-warning">Existing directory</span>' : '<span class="badge badge-success">New directory</span>'}</dd>
          </div>
        </div>

        <div class="preview-paths-section">
          <p class="preview-subtitle">Files to create:</p>
          <ul class="preview-paths-list">
            ${planned.map((p) => `<li class="mono-val">${escapeHtml(p)}</li>`).join("")}
          </ul>
        </div>

        <div class="preview-actions">
          <button type="button" id="create-apply-btn" class="btn btn-success">Confirm &amp; Create Workspace</button>
        </div>
      </div>
    `;
  }

  function renderImportTab() {
    return `
      <div class="setup-panel card" id="import-panel">
        <div class="panel-intro">
          <h2 class="section-heading">Import Existing Workspace</h2>
          <p class="section-desc">Adopt an existing LZA deployment or configuration repository into LZA Workbench.</p>
        </div>

        <form id="import-form" class="setup-form" onsubmit="return false;">
          <div class="form-group">
            <label for="import-workspace-dir">Workspace Directory <span class="required">*</span></label>
            <div class="input-action-row">
              <input type="text" id="import-workspace-dir" class="form-input flex-1" placeholder="/path/to/existing/workspace" required />
              <button type="button" id="import-inspect-btn" class="btn btn-secondary">Inspect</button>
            </div>
            <span class="field-hint">Path to the folder containing existing LZA files or git repository.</span>
          </div>

          <div class="form-group">
            <label for="import-config-dir">Configuration Directory</label>
            <input type="text" id="import-config-dir" class="form-input" placeholder="Default: &lt;workspace&gt;/config" />
            <span class="field-hint">Optional path to the directory containing LZA YAML files if not in config/.</span>
          </div>

          <details class="overrides-details" id="import-overrides-details">
            <summary class="overrides-summary">Overrides &amp; Advanced Options</summary>
            <div class="overrides-body">
              <div class="form-group">
                <label for="import-customer-name">Customer Name</label>
                <input type="text" id="import-customer-name" class="form-input" placeholder="Leave blank to auto-detect" />
              </div>

              <div class="form-row">
                <div class="form-group flex-1">
                  <label for="import-aws-region">AWS Region</label>
                  <input type="text" id="import-aws-region" class="form-input" placeholder="us-east-1" />
                </div>
                <div class="form-group flex-1">
                  <label for="import-aws-profile">AWS Profile</label>
                  <input type="text" id="import-aws-profile" class="form-input" placeholder="&lt;customer-slug&gt;-root" />
                </div>
              </div>

              <div class="form-row">
                <div class="form-group flex-1">
                  <label for="import-lza-version">LZA Version</label>
                  <input type="text" id="import-lza-version" class="form-input" placeholder="v1.15.5" />
                </div>
                <div class="form-group flex-1">
                  <label for="import-stack-name">Installer Stack Name</label>
                  <input type="text" id="import-stack-name" class="form-input" placeholder="Auto-detect" />
                </div>
              </div>

              <div class="checkbox-stack">
                <label class="checkbox-label">
                  <input type="checkbox" id="import-skip-aws" />
                  <span>Skip AWS connectivity checks (offline import)</span>
                </label>
                <label class="checkbox-label">
                  <input type="checkbox" id="import-force" />
                  <span>Force overwrite existing configuration metadata</span>
                </label>
                <label class="checkbox-label">
                  <input type="checkbox" id="import-repair" />
                  <span>Repair partial or corrupted metadata</span>
                </label>
              </div>
            </div>
          </details>

          <div class="form-actions">
            <button type="button" id="import-prepare-btn" class="btn btn-primary">Prepare Import</button>
          </div>
        </form>

        <div id="import-preview-area" ${importPreviewData ? "" : "hidden"}>
          ${importPreviewData ? renderImportPreview(importPreviewData) : ""}
        </div>
      </div>
    `;
  }

  function renderImportPreview(data) {
    const prov = data.provenance;
    const paths = data.affectedPaths || [];
    const recs = data.recommendations || [];

    return `
      <div class="preview-card">
        <h3 class="preview-title">Import Preparation Review</h3>
        <div class="kv-grid">
          <div class="kv-row">
            <dt class="kv-label">Workspace Directory</dt>
            <dd class="kv-value mono-val">${escapeHtml(data.workspaceDir)}</dd>
          </div>
          <div class="kv-row">
            <dt class="kv-label">Configuration Directory</dt>
            <dd class="kv-value mono-val">${escapeHtml(data.configDir)}</dd>
          </div>
          <div class="kv-row">
            <dt class="kv-label">Customer</dt>
            <dd class="kv-value">${escapeHtml(data.customerName)} (${escapeHtml(data.customerSlug)})</dd>
          </div>
          <div class="kv-row">
            <dt class="kv-label">Installer Stack</dt>
            <dd class="kv-value">${data.installerDiscovered ? `<span class="badge badge-success">${escapeHtml(data.discoveredStackStatus || "Discovered")}</span>` : '<span class="val-empty">Not found in AWS</span>'}</dd>
          </div>
          ${
            prov
              ? `
            <div class="kv-row">
              <dt class="kv-label">Git Provenance</dt>
              <dd class="kv-value">${escapeHtml(prov.repoType)} / ${escapeHtml(prov.branch || "unknown")}${prov.commit ? ` (${escapeHtml(prov.commit.slice(0, 7))})` : ""} &bull; ${prov.filesCount} files</dd>
            </div>
            `
              : ""
          }
          <div class="kv-row">
            <dt class="kv-label">Already Imported</dt>
            <dd class="kv-value">${data.alreadyImported ? '<span class="badge badge-warning">Yes</span>' : '<span class="badge badge-neutral">No</span>'}</dd>
          </div>
        </div>

        ${
          recs.length > 0
            ? `
          <div class="preview-recommendations">
            <p class="preview-subtitle">Recommendations &amp; Notes:</p>
            <ul class="recommendation-list">
              ${recs.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}
            </ul>
          </div>
          `
            : ""
        }

        <div class="preview-paths-section">
          <p class="preview-subtitle">Files to write or update:</p>
          <ul class="preview-paths-list">
            ${paths.map((p) => `<li class="mono-val">${escapeHtml(p)}</li>`).join("")}
          </ul>
        </div>

        <div class="preview-actions">
          <button type="button" id="import-apply-btn" class="btn btn-success">Confirm &amp; Apply Import</button>
        </div>
      </div>
    `;
  }

  function renderOpenTab(currentPath) {
    return `
      <div class="setup-panel card" id="open-panel">
        <div class="panel-intro">
          <h2 class="section-heading">Open Existing Workspace</h2>
          <p class="section-desc">Switch to an existing LZA Workbench workspace directory on your machine.</p>
        </div>

        <form id="open-form" class="setup-form" onsubmit="return false;">
          <div class="form-group">
            <label for="open-workspace-dir">Workspace Directory Path <span class="required">*</span></label>
            <input type="text" id="open-workspace-dir" class="form-input" placeholder="/path/to/workspace" value="${escapeHtml(currentPath)}" required />
            <span class="field-hint">Path to a directory containing a valid lza-workspace.yaml file.</span>
          </div>

          <div class="form-actions">
            <button type="button" id="open-submit-btn" class="btn btn-primary">Open Workspace</button>
          </div>
        </form>
      </div>
    `;
  }

  function bindTabEvents() {
    container.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        if (tab && tab !== activeTab) {
          activeTab = tab;
          setNotice("");
          render();
        }
      });
    });
  }

  function bindCreateEvents() {
    const previewBtn = container.querySelector("#create-preview-btn");
    const nameInput = container.querySelector("#create-customer-name");
    const dirInput = container.querySelector("#create-workspace-dir");
    const regionInput = container.querySelector("#create-aws-region");
    const profileInput = container.querySelector("#create-aws-profile");
    const versionInput = container.querySelector("#create-lza-version");
    const forceInput = container.querySelector("#create-force");

    if (previewBtn) {
      previewBtn.addEventListener("click", async () => {
        const customerName = (nameInput?.value || "").trim();
        if (!customerName) {
          setNotice("Customer name is required.", "error");
          nameInput?.focus();
          return;
        }

        previewBtn.disabled = true;
        setNotice("Validating workspace configuration…", "info");

        try {
          const payload = {
            customer_name: customerName,
            workspace_dir: dirInput?.value.trim() || null,
            aws_auth_type: "profile",
            aws_profile: profileInput?.value.trim() || null,
            aws_region: regionInput?.value.trim() || "us-east-1",
            lza_version: versionInput?.value.trim() || "v1.15.5",
            force: Boolean(forceInput?.checked),
            skip_aws_check: true,
          };

          createPreviewData = await previewWorkspaceInit(payload);
          setNotice("");
          render();
        } catch (err) {
          setNotice(err.message, "error");
        } finally {
          if (previewBtn) previewBtn.disabled = false;
        }
      });
    }

    const applyBtn = container.querySelector("#create-apply-btn");
    if (applyBtn) {
      applyBtn.addEventListener("click", async () => {
        const customerName = (nameInput?.value || "").trim();
        applyBtn.disabled = true;
        setNotice("Creating workspace files…", "info");

        try {
          const payload = {
            customer_name: customerName,
            workspace_dir: dirInput?.value.trim() || null,
            aws_auth_type: "profile",
            aws_profile: profileInput?.value.trim() || null,
            aws_region: regionInput?.value.trim() || "us-east-1",
            lza_version: versionInput?.value.trim() || "v1.15.5",
            force: Boolean(forceInput?.checked),
            skip_aws_check: true,
          };

          await applyWorkspaceInit(payload);
          setNotice("Workspace created successfully!", "success");
          if (onDone) {
            onDone();
          } else {
            window.location.hash = "#/overview";
          }
        } catch (err) {
          setNotice(err.message, "error");
          applyBtn.disabled = false;
        }
      });
    }
  }

  function bindImportEvents() {
    const wsDirInput = container.querySelector("#import-workspace-dir");
    const cfgDirInput = container.querySelector("#import-config-dir");
    const inspectBtn = container.querySelector("#import-inspect-btn");
    const prepareBtn = container.querySelector("#import-prepare-btn");
    const customerInput = container.querySelector("#import-customer-name");
    const regionInput = container.querySelector("#import-aws-region");
    const profileInput = container.querySelector("#import-aws-profile");
    const versionInput = container.querySelector("#import-lza-version");
    const stackInput = container.querySelector("#import-stack-name");
    const skipAwsInput = container.querySelector("#import-skip-aws");
    const forceInput = container.querySelector("#import-force");
    const repairInput = container.querySelector("#import-repair");

    if (inspectBtn) {
      inspectBtn.addEventListener("click", async () => {
        const wsDir = (wsDirInput?.value || "").trim();
        if (!wsDir) {
          setNotice("Please enter a workspace directory to inspect.", "error");
          wsDirInput?.focus();
          return;
        }
        inspectBtn.disabled = true;
        setNotice("Inspecting workspace directory…", "info");
        try {
          const discovery = await discoverWorkspaceImport({
            workspace_dir: wsDir,
            config_dir: cfgDirInput?.value.trim() || null,
            force: Boolean(forceInput?.checked),
            repair: Boolean(repairInput?.checked),
          });

          if (discovery.existingCustomerName && customerInput && !customerInput.value) {
            customerInput.value = discovery.existingCustomerName;
          }
          if (discovery.existingAwsProfile && profileInput && !profileInput.value) {
            profileInput.value = discovery.existingAwsProfile;
          }
          if (discovery.existingAwsRegion && regionInput && !regionInput.value) {
            regionInput.value = discovery.existingAwsRegion;
          }
          if (discovery.existingLzaVersion && versionInput && !versionInput.value) {
            versionInput.value = discovery.existingLzaVersion;
          }

          const msg = discovery.hasExistingMetadata
            ? `Inspection found existing metadata for customer "${discovery.existingCustomerName}". Fields pre-filled.`
            : "Directory inspected. Valid LZA configuration files found.";
          setNotice(msg, "info");
        } catch (err) {
          setNotice(err.message, "error");
        } finally {
          inspectBtn.disabled = false;
        }
      });
    }

    if (prepareBtn) {
      prepareBtn.addEventListener("click", async () => {
        const wsDir = (wsDirInput?.value || "").trim();
        if (!wsDir) {
          setNotice("Workspace directory is required.", "error");
          wsDirInput?.focus();
          return;
        }

        prepareBtn.disabled = true;
        setNotice("Preparing import discovery and checking resources…", "info");

        try {
          const payload = {
            workspace_dir: wsDir,
            config_dir: cfgDirInput?.value.trim() || null,
            customer_name: customerInput?.value.trim() || null,
            aws_auth_type: "profile",
            aws_profile: profileInput?.value.trim() || null,
            aws_region: regionInput?.value.trim() || "us-east-1",
            lza_version: versionInput?.value.trim() || "v1.15.5",
            installer_stack_name: stackInput?.value.trim() || null,
            skip_aws_check: Boolean(skipAwsInput?.checked),
            force: Boolean(forceInput?.checked),
            repair: Boolean(repairInput?.checked),
          };

          importPreviewData = await prepareWorkspaceImport(payload);
          setNotice("");
          render();
        } catch (err) {
          setNotice(err.message, "error");
        } finally {
          if (prepareBtn) prepareBtn.disabled = false;
        }
      });
    }

    const applyBtn = container.querySelector("#import-apply-btn");
    if (applyBtn) {
      applyBtn.addEventListener("click", async () => {
        applyBtn.disabled = true;
        setNotice("Applying workspace import…", "info");

        try {
          await applyWorkspaceImport();
          setNotice("Workspace imported successfully!", "success");
          if (onDone) {
            onDone();
          } else {
            window.location.hash = "#/overview";
          }
        } catch (err) {
          setNotice(err.message, "error");
          applyBtn.disabled = false;
        }
      });
    }
  }

  function bindOpenEvents() {
    const submitBtn = container.querySelector("#open-submit-btn");
    const dirInput = container.querySelector("#open-workspace-dir");

    if (submitBtn) {
      submitBtn.addEventListener("click", async () => {
        const dir = (dirInput?.value || "").trim();
        if (!dir) {
          setNotice("Workspace directory path is required.", "error");
          dirInput?.focus();
          return;
        }

        submitBtn.disabled = true;
        setNotice("Validating and opening workspace…", "info");

        try {
          await openWorkspace(dir);
          setNotice("Workspace opened successfully!", "success");
          if (onDone) {
            onDone();
          } else {
            window.location.hash = "#/overview";
          }
        } catch (err) {
          setNotice(err.message, "error");
          submitBtn.disabled = false;
        }
      });
    }
  }

  render();
}
