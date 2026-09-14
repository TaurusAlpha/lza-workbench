import {
  applyConfigDeploy,
  getActiveWorkspace,
  getConfigurationStatus,
  getInstallerStatus,
  getPipelineDiagnostics,
  getPipelineSnapshot,
  getStatus,
  openWorkspace,
} from "./api.js";
import { renderConfigurationDetails } from "./configuration.js";
import { renderInstallerDetails } from "./installer.js";
import { escapeHtml, renderOverview } from "./overview.js";
import { renderPipelineDetails } from "./pipeline.js";
import { getRecentWorkspaces, recordRecentWorkspace } from "./recents.js";
import { renderSetup } from "./setup.js";
import { renderWelcome } from "./welcome.js";

const viewContent = document.querySelector("#view-content") || document.querySelector("#overview");
const notice = document.querySelector("#notice");
const workspacePath = document.querySelector("#workspace-path");
const refresh = document.querySelector("#refresh");
const pageEyebrow = document.querySelector("#page-eyebrow");
const pageTitle = document.querySelector("#page-title");
const breadcrumb = document.querySelector("#breadcrumb");
const pageHeader = document.querySelector("#page-header");

// Navbar elements
const mainNav = document.querySelector("#main-nav");
const wsSwitcherBtn = document.querySelector("#ws-switcher-btn");
const wsSwitcherMenu = document.querySelector("#ws-switcher-menu");
const wsSwitcherName = document.querySelector("#ws-switcher-name");
const wsSwitcherDot = document.querySelector("#ws-switcher-dot");
const wsMenuRecents = document.querySelector("#ws-menu-recents");
const awsStatusChip = document.querySelector("#aws-status-chip");
const awsStatusLabel = document.querySelector("#aws-status-label");
const themeToggle = document.querySelector("#theme-toggle");
const toastContainer = document.querySelector("#toast-container");

// Offline bar elements
const offlineBar = document.querySelector("#offline-bar");
const offlineCmdWrapper = document.querySelector("#offline-cmd-wrapper");
const offlineCmdText = document.querySelector("#offline-cmd-text");
const offlineCmdCopy = document.querySelector("#offline-cmd-copy");
const offlineDetailsBtn = document.querySelector("#offline-details-btn");
const offlineDismissBtn = document.querySelector("#offline-dismiss-btn");
const offlineDetailsPanel = document.querySelector("#offline-details-panel");
const offlineDetailsText = document.querySelector("#offline-details-text");

let pipelinePollTimer = null;
let currentActiveWorkspace = null;
let currentAwsState = null;

// ==========================================
// Toast Notification System
// ==========================================
export function showToast(message, type = "info", duration = 3500) {
  if (!toastContainer) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-content">
      <span class="toast-icon"></span>
      <span class="toast-msg">${escapeHtml(message)}</span>
    </div>
    <button type="button" class="toast-close" aria-label="Close">&times;</button>
  `;

  const closeBtn = toast.querySelector(".toast-close");
  const removeToast = () => {
    toast.classList.add("toast-hiding");
    toast.addEventListener("animationend", () => toast.remove());
  };

  closeBtn.addEventListener("click", removeToast);
  toastContainer.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => {
      if (toast.parentElement) removeToast();
    }, duration);
  }
}

// ==========================================
// Theme Management
// ==========================================
function initTheme() {
  const savedTheme = localStorage.getItem("lza_theme") || "dark";
  applyTheme(savedTheme);

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      applyTheme(next);
      localStorage.setItem("lza_theme", next);
    });
  }
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const sun = document.querySelector(".theme-icon-sun");
  const moon = document.querySelector(".theme-icon-moon");
  if (sun && moon) {
    if (theme === "light") {
      sun.hidden = false;
      moon.hidden = true;
    } else {
      sun.hidden = true;
      moon.hidden = false;
    }
  }
}

// ==========================================
// Workspace Switcher Dropdown
// ==========================================
function updateWorkspaceSwitcher(ws) {
  currentActiveWorkspace = ws;
  if (!wsSwitcherName) return;

  if (ws && ws.hasWorkspace) {
    wsSwitcherName.textContent = ws.customerName || "Customer Workspace";
    wsSwitcherName.title = `${ws.customerName || "Workspace"} (${ws.workspaceDir})`;
    if (wsSwitcherDot) wsSwitcherDot.className = "ws-switcher-dot active";
  } else {
    wsSwitcherName.textContent = "No Active Workspace";
    wsSwitcherName.removeAttribute("title");
    if (wsSwitcherDot) wsSwitcherDot.className = "ws-switcher-dot";
  }
  renderSwitcherRecents();
}

function renderSwitcherRecents() {
  if (!wsMenuRecents) return;
  const recents = getRecentWorkspaces();
  if (recents.length === 0) {
    wsMenuRecents.innerHTML = `<div class="ws-menu-empty">No recent workspaces</div>`;
    return;
  }

  wsMenuRecents.innerHTML = recents
    .map(
      (item) => `
      <div class="ws-recent-item" data-dir="${escapeHtml(item.workspaceDir)}">
        <div class="ws-recent-info">
          <strong class="ws-recent-title">${escapeHtml(item.customerName)}</strong>
          <span class="ws-recent-path" title="${escapeHtml(item.workspaceDir)}">${escapeHtml(item.workspaceDir)}</span>
        </div>
        <span class="ws-recent-badge badge badge-neutral">${escapeHtml(item.lzaVersion || "v1.15.5")}</span>
      </div>
    `
    )
    .join("");

  wsMenuRecents.querySelectorAll(".ws-recent-item").forEach((el) => {
    el.addEventListener("click", async () => {
      const dir = el.dataset.dir;
      closeSwitcherMenu();
      try {
        const res = await openWorkspace(dir);
        recordRecentWorkspace({
          customerName: res.customerName,
          workspaceDir: res.workspaceDir,
          lzaVersion: res.lzaVersion,
        });
        showToast(`Switched to workspace: ${res.customerName}`, "success");
        window.location.hash = "#/overview";
        handleRoute();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });
}

function toggleSwitcherMenu() {
  if (!wsSwitcherMenu) return;
  const isHidden = wsSwitcherMenu.hidden;
  if (isHidden) {
    renderSwitcherRecents();
    wsSwitcherMenu.hidden = false;
    wsSwitcherBtn.setAttribute("aria-expanded", "true");
  } else {
    closeSwitcherMenu();
  }
}

function closeSwitcherMenu() {
  if (!wsSwitcherMenu) return;
  wsSwitcherMenu.hidden = true;
  if (wsSwitcherBtn) wsSwitcherBtn.setAttribute("aria-expanded", "false");
}

if (wsSwitcherBtn) {
  wsSwitcherBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleSwitcherMenu();
  });
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#ws-switcher")) {
    closeSwitcherMenu();
  }
});

// ==========================================
// AWS Status & Offline Bar Management
// ==========================================
function updateAwsStatus(aws) {
  if (!awsStatusChip || !awsStatusLabel) return;
  if (aws && aws.isLive) {
    awsStatusChip.className = "aws-status-pill live";
    const accountStr = aws.identity?.account ? ` (${aws.identity.account})` : "";
    const regionStr = aws.region ? ` [${aws.region}]` : "";
    awsStatusLabel.textContent = `AWS Live${regionStr}`;
    awsStatusChip.title = `AWS Live: Profile ${aws.profile || "default"}${accountStr}${regionStr}`;
  } else {
    awsStatusChip.className = "aws-status-pill offline";
    awsStatusLabel.textContent = "AWS Offline";
    awsStatusChip.title = "AWS Offline. Click to view details and authentication instructions.";
  }
}

function updateOfflineStatus(aws) {
  currentAwsState = aws;
  updateAwsStatus(aws);

  if (!offlineBar) return;

  if (aws && aws.isLive) {
    offlineBar.hidden = true;
    return;
  }

  // If dismissed, keep banner closed across refreshes/navigations
  const isDismissed = localStorage.getItem("lza_offline_dismissed") === "true";
  if (isDismissed) {
    offlineBar.hidden = true;
    return;
  }

  // Populate details
  const errorMsg = aws?.error || "AWS authentication or connectivity is inactive.";
  if (offlineDetailsText) offlineDetailsText.textContent = errorMsg;

  // Extract actionable SSO command if present
  const match = errorMsg.match(/Run '([^']+)'/i) || errorMsg.match(/(aws sso login [^\s.'"]+)/i);
  if (match && match[1] && offlineCmdWrapper && offlineCmdText) {
    offlineCmdText.textContent = match[1];
    offlineCmdWrapper.hidden = false;
    if (offlineCmdCopy) offlineCmdCopy.dataset.copy = match[1];
  } else if (offlineCmdWrapper) {
    offlineCmdWrapper.hidden = true;
  }

  offlineBar.hidden = false;
}

if (offlineDismissBtn) {
  offlineDismissBtn.addEventListener("click", () => {
    if (offlineBar) offlineBar.hidden = true;
    localStorage.setItem("lza_offline_dismissed", "true");
    showToast("Working in offline mode. Details remain accessible via the top status pill.", "info", 3500);
  });
}

if (offlineDetailsBtn) {
  offlineDetailsBtn.addEventListener("click", () => {
    if (offlineDetailsPanel) {
      offlineDetailsPanel.hidden = !offlineDetailsPanel.hidden;
      offlineDetailsBtn.textContent = offlineDetailsPanel.hidden ? "Details" : "Hide Details";
    }
  });
}

if (offlineCmdCopy) {
  offlineCmdCopy.addEventListener("click", async () => {
    const text = offlineCmdCopy.dataset.copy;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      offlineCmdCopy.classList.add("copied");
      showToast("Authentication command copied to clipboard", "success", 2500);
      setTimeout(() => offlineCmdCopy.classList.remove("copied"), 1500);
    } catch (e) {
      console.warn("Clipboard copy failed:", e);
    }
  });
}

if (awsStatusChip) {
  awsStatusChip.addEventListener("click", () => {
    if (!offlineBar) return;
    if (currentAwsState && !currentAwsState.isLive) {
      const isNowHidden = !offlineBar.hidden;
      offlineBar.hidden = isNowHidden;
      if (isNowHidden) {
        localStorage.setItem("lza_offline_dismissed", "true");
      } else {
        localStorage.removeItem("lza_offline_dismissed");
      }
    }
  });
}

// ==========================================
// Navigation Highlight
// ==========================================
function updateNavHighlight(routeName) {
  if (!mainNav) return;
  mainNav.querySelectorAll(".nav-link").forEach((link) => {
    const route = link.dataset.route;
    if (route === routeName) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
}

// ==========================================
// Polling & Routing
// ==========================================
function stopPipelinePolling() {
  if (pipelinePollTimer) {
    clearInterval(pipelinePollTimer);
    pipelinePollTimer = null;
  }
}

function parseRoute() {
  const hash = (window.location.hash || "").replace(/^#/, "").trim();
  const [pathPart, queryPart] = hash.split("?");
  const clean = (pathPart || "").replace(/^\/?/, "/");
  const params = new URLSearchParams(queryPart || "");
  const executionId = params.get("executionId") || params.get("execution_id");

  if (clean === "/welcome") {
    return { name: "welcome" };
  }
  if (clean === "/" || clean === "/overview") {
    return { name: "overview" };
  }
  if (clean === "/setup") {
    return { name: "setup" };
  }
  if (clean === "/installer") {
    return { name: "installer" };
  }
  if (clean === "/configuration") {
    return { name: "configuration" };
  }
  if (clean === "/pipeline/installer") {
    return { name: "pipeline", pipelineType: "installer", executionId };
  }
  if (clean === "/pipeline/configuration" || clean === "/configuration-pipeline") {
    return { name: "pipeline", pipelineType: "configuration", executionId };
  }
  return { name: "overview" };
}

function clearNotice() {
  notice.replaceChildren();
  notice.textContent = "";
  notice.className = "notice";
  notice.hidden = true;
}

function showNotice(text, type = "warning") {
  notice.textContent = text;
  notice.className = `notice ${type}`;
  notice.hidden = false;
}

// ==========================================
// View Loaders
// ==========================================
async function loadWelcome() {
  stopPipelinePolling();
  updateNavHighlight("welcome");
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;

  if (pageHeader) pageHeader.hidden = true;
  if (breadcrumb) breadcrumb.hidden = true;

  let activeWs = null;
  try {
    activeWs = await getActiveWorkspace();
    if (activeWs && activeWs.hasWorkspace) {
      updateWorkspaceSwitcher(activeWs);
    }
  } catch {
    activeWs = null;
  }

  renderWelcome(
    viewContent,
    activeWs,
    (openedWs) => {
      updateWorkspaceSwitcher({
        hasWorkspace: true,
        customerName: openedWs.customerName,
        workspaceDir: openedWs.workspaceDir,
      });
      window.location.hash = "#/overview";
      handleRoute();
    },
    showToast
  );

  viewContent.setAttribute("aria-busy", "false");
  refresh.disabled = false;
}

async function loadOverview() {
  updateNavHighlight("overview");
  if (pageHeader) pageHeader.hidden = false;
  viewContent.className = "card-grid";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;
  if (breadcrumb) breadcrumb.hidden = true;

  try {
    const status = await getStatus();

    if (pageEyebrow) pageEyebrow.textContent = "Workspace Overview";
    if (pageTitle) pageTitle.textContent = status.workspace.customerName || "Default Workspace";
    if (workspacePath) {
      workspacePath.textContent = "";
      workspacePath.hidden = true;
    }

    // Record recents and update switcher
    recordRecentWorkspace({
      customerName: status.workspace.customerName,
      workspaceDir: status.workspace.directory,
      lzaVersion: status.workspace.lzaVersion,
    });
    updateWorkspaceSwitcher({
      hasWorkspace: true,
      customerName: status.workspace.customerName,
      workspaceDir: status.workspace.directory,
    });
    updateOfflineStatus(status.aws);

    renderOverview(viewContent, status);
    clearNotice();
  } catch (error) {
    if (
      error.message?.includes("No active workspace") ||
      error.message?.includes("No workspace") ||
      error.message?.includes("workspace_unavailable")
    ) {
      updateWorkspaceSwitcher({ hasWorkspace: false });
      window.location.hash = "#/welcome";
      return;
    }
    workspacePath.textContent = "Workspace status unavailable";
    workspacePath.removeAttribute("title");
    viewContent.replaceChildren();
    showNotice(error.message, "error");
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

async function loadConfiguration() {
  updateNavHighlight("configuration");
  if (pageHeader) pageHeader.hidden = false;
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;
  if (pageEyebrow) pageEyebrow.textContent = "LZA Workbench / Configuration";
  if (pageTitle) pageTitle.textContent = "Configuration Details";
  if (breadcrumb) breadcrumb.hidden = false;

  try {
    const status = await getConfigurationStatus();
    if (workspacePath) {
      workspacePath.hidden = false;
      workspacePath.textContent = status.workspace.directory;
      workspacePath.title = status.workspace.directory;
    }
    renderConfigurationDetails(viewContent, status, loadConfiguration);
    updateOfflineStatus({ isLive: status.workspace.isLive, error: status.workspace.error });
    clearNotice();
  } catch (error) {
    workspacePath.textContent = "Configuration status unavailable";
    workspacePath.removeAttribute("title");
    viewContent.replaceChildren();
    showNotice(error.message, "error");
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

async function loadPipeline(pipelineType = "configuration", executionId = null) {
  stopPipelinePolling();
  updateNavHighlight("pipeline");
  if (pageHeader) pageHeader.hidden = false;
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;

  const isInstaller = pipelineType === "installer";
  if (pageEyebrow) {
    pageEyebrow.textContent = isInstaller
      ? "LZA Workbench / Installer Pipeline"
      : "LZA Workbench / Configuration Pipeline";
  }
  if (pageTitle) {
    pageTitle.textContent = isInstaller
      ? "Installer Pipeline Details"
      : "Configuration Pipeline Details";
  }
  if (breadcrumb) breadcrumb.hidden = false;

  let currentDiagnostics = null;

  async function fetchAndRenderDiagnostics(snap) {
    try {
      currentDiagnostics = await getPipelineDiagnostics({
        type: pipelineType,
        executionId: snap.executionId || executionId,
      });
      renderPipelineDetails(
        viewContent,
        snap,
        () => loadPipeline(pipelineType, executionId),
        currentDiagnostics,
        () => fetchAndRenderDiagnostics(snap)
      );
    } catch (e) {
      console.warn("Diagnostics fetch failed:", e);
    }
  }

  try {
    const snapshot = await getPipelineSnapshot({
      type: pipelineType,
      executionId,
    });

    workspacePath.textContent = snapshot.pipelineName;
    workspacePath.title = snapshot.pipelineArn;

    if (snapshot.status === "Failed") {
      try {
        currentDiagnostics = await getPipelineDiagnostics({
          type: pipelineType,
          executionId: snapshot.executionId || executionId,
        });
      } catch {
        currentDiagnostics = null;
      }
    }

    renderPipelineDetails(
      viewContent,
      snapshot,
      () => loadPipeline(pipelineType, executionId),
      currentDiagnostics,
      () => fetchAndRenderDiagnostics(snapshot)
    );

    updateOfflineStatus({ isLive: snapshot.isLive, error: snapshot.error });
    clearNotice();

    // Single-pass periodic polling while active (not terminal)
    if (!snapshot.isTerminal && snapshot.isLive) {
      pipelinePollTimer = setInterval(async () => {
        try {
          const snap = await getPipelineSnapshot({
            type: pipelineType,
            executionId: snapshot.executionId || executionId,
          });
          if (snap.status === "Failed" && !currentDiagnostics) {
            currentDiagnostics = await getPipelineDiagnostics({
              type: pipelineType,
              executionId: snap.executionId || executionId,
            }).catch(() => null);
          }
          renderPipelineDetails(
            viewContent,
            snap,
            () => loadPipeline(pipelineType, executionId),
            currentDiagnostics,
            () => fetchAndRenderDiagnostics(snap)
          );
          if (snap.isTerminal) {
            stopPipelinePolling();
          }
        } catch (err) {
          console.warn("Pipeline poll iteration failed:", err);
        }
      }, 3000);
    }
  } catch (error) {
    workspacePath.textContent = "Pipeline status unavailable";
    workspacePath.removeAttribute("title");
    viewContent.replaceChildren();
    showNotice(error.message, "error");
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

async function loadInstaller() {
  stopPipelinePolling();
  updateNavHighlight("installer");
  if (pageHeader) pageHeader.hidden = false;
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;
  if (pageEyebrow) pageEyebrow.textContent = "LZA Workbench / Installer";
  if (pageTitle) pageTitle.textContent = "Installer Settings & Deployment";
  if (breadcrumb) breadcrumb.hidden = false;

  try {
    const status = await getInstallerStatus();
    workspacePath.textContent = status.workspace.directory;
    workspacePath.title = status.workspace.directory;
    renderInstallerDetails(viewContent, status, loadInstaller);
    updateOfflineStatus(status.aws);
    clearNotice();
  } catch (error) {
    workspacePath.textContent = "Installer status unavailable";
    workspacePath.removeAttribute("title");
    viewContent.replaceChildren();
    showNotice(error.message, "error");
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

async function loadSetup() {
  stopPipelinePolling();
  updateNavHighlight("overview");
  if (pageHeader) pageHeader.hidden = false;
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;

  if (pageEyebrow) pageEyebrow.textContent = "LZA Workbench / Setup";
  if (pageTitle) pageTitle.textContent = "Workspace Setup";

  let activeWs = null;
  try {
    activeWs = await getActiveWorkspace();
  } catch {
    activeWs = null;
  }

  const hasActive = activeWs && activeWs.hasWorkspace;
  if (breadcrumb) {
    breadcrumb.hidden = !hasActive;
  }

  if (hasActive) {
    workspacePath.textContent = activeWs.workspaceDir;
    workspacePath.title = activeWs.workspaceDir;
    updateWorkspaceSwitcher(activeWs);
  } else {
    workspacePath.textContent = "No active workspace";
    workspacePath.removeAttribute("title");
    updateWorkspaceSwitcher({ hasWorkspace: false });
  }

  renderSetup(viewContent, activeWs, () => {
    window.location.hash = "#/overview";
    handleRoute();
  });

  viewContent.setAttribute("aria-busy", "false");
  refresh.disabled = false;
}

function handleRoute() {
  stopPipelinePolling();
  const route = parseRoute();
  if (route.name === "welcome") {
    loadWelcome();
  } else if (route.name === "setup") {
    loadSetup();
  } else if (route.name === "installer") {
    loadInstaller();
  } else if (route.name === "configuration") {
    loadConfiguration();
  } else if (route.name === "pipeline") {
    loadPipeline(route.pipelineType, route.executionId);
  } else {
    loadOverview();
  }
}

// Initial setup
initTheme();
refresh.addEventListener("click", handleRoute);
window.addEventListener("hashchange", handleRoute);
handleRoute();
