import {
  applyConfigDeploy,
  getActiveWorkspace,
  getBootstrapPlan,
  getConfigurationStatus,
  getInstallerStatus,
  getPipelineDiagnostics,
  getPipelineSnapshot,
  getStatus,
} from "./api.js";
import { renderBootstrapDetails } from "./bootstrap.js";
import { renderConfigurationDetails } from "./configuration.js";
import { renderInstallerDetails } from "./installer.js";
import { renderOverview } from "./overview.js";
import { renderPipelineDetails } from "./pipeline.js";
import { renderSetup } from "./setup.js";

const viewContent = document.querySelector("#view-content") || document.querySelector("#overview");
const notice = document.querySelector("#notice");
const workspacePath = document.querySelector("#workspace-path");
const refresh = document.querySelector("#refresh");
const pageEyebrow = document.querySelector("#page-eyebrow");
const pageTitle = document.querySelector("#page-title");
const breadcrumb = document.querySelector("#breadcrumb");

let pipelinePollTimer = null;

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
  if (clean === "/bootstrap") {
    return { name: "bootstrap" };
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

function getOfflineWarning(awsError) {
  const reason = awsError ? `: ${awsError}` : "";
  return `AWS is offline${reason}. Displayed deployment, stack, and pipeline statuses are not live and reflect the last recorded state.`;
}

async function loadOverview() {
  viewContent.className = "card-grid";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;
  if (pageEyebrow) pageEyebrow.textContent = "LZA Workbench";
  if (pageTitle) pageTitle.textContent = "Workspace Overview";
  if (breadcrumb) breadcrumb.hidden = true;

  try {
    const [status, bootstrapPlan] = await Promise.all([
      getStatus(),
      getBootstrapPlan().catch(() => null),
    ]);
    workspacePath.textContent = status.workspace.directory;
    workspacePath.title = status.workspace.directory;
    renderOverview(viewContent, status, bootstrapPlan);
    if (!status.aws.isLive) {
      showNotice(getOfflineWarning(status.aws.error), "warning");
    } else {
      clearNotice();
    }
  } catch (error) {
    if (
      error.message?.includes("No active workspace") ||
      error.message?.includes("No workspace") ||
      error.message?.includes("workspace_unavailable")
    ) {
      window.location.hash = "#/setup";
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
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;
  if (pageEyebrow) pageEyebrow.textContent = "LZA Workbench / Configuration";
  if (pageTitle) pageTitle.textContent = "Configuration Details";
  if (breadcrumb) breadcrumb.hidden = false;

  try {
    const status = await getConfigurationStatus();
    workspacePath.textContent = status.workspace.directory;
    workspacePath.title = status.workspace.directory;
    renderConfigurationDetails(viewContent, status, loadConfiguration);
    if (!status.workspace.isLive) {
      showNotice(getOfflineWarning(status.workspace.error), "warning");
    } else {
      clearNotice();
    }
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

    if (!snapshot.isLive) {
      showNotice(getOfflineWarning(snapshot.error), "warning");
    } else {
      clearNotice();
    }

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
    if (!status.aws.isLive) {
      showNotice(getOfflineWarning(status.aws.error), "warning");
    } else {
      clearNotice();
    }
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

async function loadBootstrap() {
  stopPipelinePolling();
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;
  if (pageEyebrow) pageEyebrow.textContent = "LZA Workbench / Bootstrap";
  if (pageTitle) pageTitle.textContent = "Workspace Bootstrap";
  if (breadcrumb) breadcrumb.hidden = false;

  try {
    const plan = await getBootstrapPlan();
    renderBootstrapDetails(viewContent, plan, loadBootstrap);
    if (!plan.isLive) {
      showNotice(getOfflineWarning(plan.error), "warning");
    } else {
      clearNotice();
    }
  } catch (error) {
    viewContent.replaceChildren();
    showNotice(error.message, "error");
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

async function loadSetup() {
  stopPipelinePolling();
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
  } else {
    workspacePath.textContent = "No active workspace";
    workspacePath.removeAttribute("title");
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
  if (route.name === "setup") {
    loadSetup();
  } else if (route.name === "installer") {
    loadInstaller();
  } else if (route.name === "configuration") {
    loadConfiguration();
  } else if (route.name === "bootstrap") {
    loadBootstrap();
  } else if (route.name === "pipeline") {
    loadPipeline(route.pipelineType, route.executionId);
  } else {
    loadOverview();
  }
}

refresh.addEventListener("click", handleRoute);
window.addEventListener("hashchange", handleRoute);
handleRoute();
