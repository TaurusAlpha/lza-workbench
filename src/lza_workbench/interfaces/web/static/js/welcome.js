/**
 * Welcome & Onboarding view for LZA Workbench.
 */

import { openWorkspace } from "./api.js";
import { escapeHtml } from "./overview.js";
import { getRecentWorkspaces, recordRecentWorkspace, removeRecentWorkspace } from "./recents.js";

function formatRelativeTime(timestamp) {
  if (!timestamp) return "Recently";
  const diffSec = Math.floor((Date.now() - timestamp) / 1000);
  if (diffSec < 60) return "Just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function renderWelcome(container, activeWorkspace = null, onWorkspaceSelected = null, showToast = null) {
  function render() {
    const recents = getRecentWorkspaces();
    const hasActive = activeWorkspace && activeWorkspace.hasWorkspace;

    container.innerHTML = `
      <div class="welcome-container">
        <!-- Hero Section -->
        <section class="welcome-hero">
          <div class="welcome-hero-badge">AWS Landing Zone Accelerator</div>
          <h1 class="welcome-hero-title">LZA Workbench</h1>
          <p class="welcome-hero-desc">
            Local engineering control center for AWS Landing Zone Accelerator workspaces.
            Streamline installer deployments, configuration synchronization, and pipeline monitoring.
          </p>
          ${
            hasActive
              ? `
            <div class="welcome-active-banner">
              <span class="active-dot"></span>
              <span>Active Workspace: <strong>${escapeHtml(activeWorkspace.customerName || "Customer")}</strong> (${escapeHtml(activeWorkspace.workspaceDir)})</span>
              <a href="#/overview" class="btn btn-sm btn-primary">Go to Overview &rarr;</a>
            </div>
          `
              : ""
          }
        </section>

        <!-- Quick Actions Grid -->
        <section class="welcome-actions-grid">
          <!-- Open Existing -->
          <div class="welcome-action-card card">
            <div class="action-card-icon open-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <h2 class="action-card-title">Open Workspace</h2>
            <p class="action-card-desc">Load an existing customer workspace directory from your local filesystem.</p>
            <form id="welcome-open-form" class="welcome-open-form">
              <div class="input-with-action">
                <input
                  type="text"
                  id="welcome-open-path"
                  class="form-input form-input-sm"
                  placeholder="/path/to/customer/workspace"
                  required
                />
                <button type="submit" id="welcome-open-btn" class="btn btn-sm btn-primary">Open</button>
              </div>
            </form>
          </div>

          <!-- Create New -->
          <div class="welcome-action-card card">
            <div class="action-card-icon create-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
            </div>
            <h2 class="action-card-title">Create Workspace</h2>
            <p class="action-card-desc">Initialize a clean, declarative customer workspace with custom AWS context and parameters.</p>
            <a href="#/setup" class="btn btn-sm btn-outline action-card-btn">Initialize New Workspace &rarr;</a>
          </div>

          <!-- Import Existing -->
          <div class="welcome-action-card card">
            <div class="action-card-icon import-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="16 16 12 12 8 16"/>
                <line x1="12" y1="12" x2="12" y2="21"/>
                <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
              </svg>
            </div>
            <h2 class="action-card-title">Import Existing LZA</h2>
            <p class="action-card-desc">Discover and adopt existing LZA configurations or repositories into Workbench management.</p>
            <a href="#/setup" class="btn btn-sm btn-outline action-card-btn" id="welcome-import-link">Import Environment &rarr;</a>
          </div>
        </section>

        <!-- Recent Workspaces Section -->
        <section class="welcome-recents-section">
          <div class="section-header-row">
            <div>
              <h2 class="section-title">Recent Workspaces</h2>
              <p class="section-subtitle">Quickly resume working on recently opened customer environments</p>
            </div>
            ${
              recents.length > 0
                ? `<button type="button" id="btn-clear-recents" class="btn btn-sm btn-ghost text-muted">Clear History</button>`
                : ""
            }
          </div>

          ${
            recents.length === 0
              ? `
            <div class="welcome-empty-recents card">
              <div class="empty-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12 6 12 12 14 14"/>
                </svg>
              </div>
              <p class="empty-title">No Recent Workspaces</p>
              <p class="empty-desc">Workspaces you open or create will be saved here for fast one-click access.</p>
            </div>
          `
              : `
            <div class="recents-grid">
              ${recents
                .map(
                  (item) => `
                <div class="recent-card card">
                  <div class="recent-card-body">
                    <div class="recent-card-header">
                      <strong class="recent-name" title="${escapeHtml(item.customerName)}">${escapeHtml(item.customerName)}</strong>
                      <span class="recent-version badge badge-neutral">${escapeHtml(item.lzaVersion || "v1.15.5")}</span>
                    </div>
                    <code class="recent-path" title="${escapeHtml(item.workspaceDir)}">${escapeHtml(item.workspaceDir)}</code>
                    <div class="recent-card-footer">
                      <span class="recent-time text-muted">${formatRelativeTime(item.lastOpenedAt)}</span>
                      <div class="recent-actions">
                        <button type="button" class="btn btn-sm btn-primary btn-open-recent" data-dir="${escapeHtml(item.workspaceDir)}">
                          Open
                        </button>
                        <button type="button" class="btn btn-sm btn-ghost btn-remove-recent" data-dir="${escapeHtml(item.workspaceDir)}" title="Remove from recents">
                          &times;
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              `
                )
                .join("")}
            </div>
          `
          }
        </section>

        <!-- Lifecycle & Architecture Guide -->
        <section class="welcome-guide-section">
          <h2 class="section-title">LZA Workbench Lifecycle</h2>
          <p class="section-subtitle">Structured progression from empty workspace to operational landing zone</p>

          <div class="lifecycle-guide-grid">
            <div class="lifecycle-step-card card">
              <div class="step-badge">Phase 1</div>
              <h3 class="step-title">Workspace Setup</h3>
              <p class="step-desc">Establishes <code>lza-workspace.yaml</code> with customer name, AWS auth profile, and target regions.</p>
              <div class="step-cli-tag"><code>lza init</code></div>
            </div>

            <div class="lifecycle-step-card card">
              <div class="step-badge">Phase 2</div>
              <h3 class="step-title">AWS Prerequisites</h3>
              <p class="step-desc">Ensures pre-requisite S3 staging buckets, KMS keys, and source code repositories exist in AWS.</p>
            </div>

            <div class="lifecycle-step-card card">
              <div class="step-badge">Phase 3</div>
              <h3 class="step-title">Installer Deployment</h3>
              <p class="step-desc">Deploys the core CloudFormation Landing Zone Accelerator Installer pipeline stack into your root account.</p>
              <div class="step-cli-tag"><code>lza installer deploy</code></div>
            </div>

            <div class="lifecycle-step-card card">
              <div class="step-badge">Phase 4</div>
              <h3 class="step-title">Config &amp; Pipelines</h3>
              <p class="step-desc">Manages customer <code>aws-accelerator-config</code>, synchronizes Git branches, and monitors pipeline runs.</p>
              <div class="step-cli-tag"><code>lza config push</code></div>
            </div>
          </div>
        </section>
      </div>
    `;

    bindEvents();
  }

  function bindEvents() {
    // Open workspace form
    const openForm = container.querySelector("#welcome-open-form");
    if (openForm) {
      openForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = container.querySelector("#welcome-open-path");
        const dir = input ? input.value.trim() : "";
        if (!dir) return;

        const submitBtn = container.querySelector("#welcome-open-btn");
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "Opening…";
        }

        try {
          const res = await openWorkspace(dir);
          recordRecentWorkspace({
            customerName: res.customerName,
            workspaceDir: res.workspaceDir,
            lzaVersion: res.lzaVersion,
          });
          if (showToast) showToast(`Workspace "${res.customerName}" opened successfully`, "success");
          if (onWorkspaceSelected) onWorkspaceSelected(res);
        } catch (err) {
          if (showToast) {
            showToast(err.message, "error");
          } else {
            alert(err.message);
          }
        } finally {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = "Open";
          }
        }
      });
    }

    // Recent open buttons
    container.querySelectorAll(".btn-open-recent").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const dir = btn.dataset.dir;
        btn.disabled = true;
        btn.textContent = "Opening…";
        try {
          const res = await openWorkspace(dir);
          recordRecentWorkspace({
            customerName: res.customerName,
            workspaceDir: res.workspaceDir,
            lzaVersion: res.lzaVersion,
          });
          if (showToast) showToast(`Workspace "${res.customerName}" opened successfully`, "success");
          if (onWorkspaceSelected) onWorkspaceSelected(res);
        } catch (err) {
          if (showToast) {
            showToast(err.message, "error");
          } else {
            alert(err.message);
          }
        } finally {
          btn.disabled = false;
          btn.textContent = "Open";
        }
      });
    });

    // Recent remove buttons
    container.querySelectorAll(".btn-remove-recent").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const dir = btn.dataset.dir;
        removeRecentWorkspace(dir);
        render();
      });
    });

    // Clear recents
    const clearBtn = container.querySelector("#btn-clear-recents");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        if (confirm("Clear all recent workspaces from this browser?")) {
          clearRecentWorkspaces();
          render();
        }
      });
    }
  }

  render();
}
