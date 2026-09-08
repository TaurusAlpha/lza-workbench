import { getConfigurationStatus, getInstallerStatus, getStatus } from "./api.js";
import { renderConfigurationDetails } from "./configuration.js";
import { renderInstallerDetails } from "./installer.js";
import { renderOverview } from "./overview.js";
import { renderPipelineDetails } from "./pipeline.js";

const viewContent = document.querySelector("#view-content") || document.querySelector("#overview");
const notice = document.querySelector("#notice");
const workspacePath = document.querySelector("#workspace-path");
const refresh = document.querySelector("#refresh");
const pageEyebrow = document.querySelector("#page-eyebrow");
const pageTitle = document.querySelector("#page-title");
const breadcrumb = document.querySelector("#breadcrumb");

function parseRoute() {
  const hash = (window.location.hash || "").replace(/^#/, "").trim();
  // Normalize: "", "/", "/overview" all resolve to "overview"
  const clean = hash.replace(/^\/?/, "/");
  if (clean === "/" || clean === "/overview") {
    return "overview";
  }
  if (clean === "/installer") {
    return "installer";
  }
  if (clean === "/configuration") {
    return "configuration";
  }
  if (clean === "/configuration-pipeline" || clean === "/pipeline/configuration") {
    return "configuration-pipeline";
  }
  return "overview";
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
    const status = await getStatus();
    workspacePath.textContent = status.workspace.directory;
    workspacePath.title = status.workspace.directory;
    renderOverview(viewContent, status);
    if (!status.aws.isLive) {
      showNotice(getOfflineWarning(status.aws.error), "warning");
    } else {
      clearNotice();
    }
  } catch (error) {
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
    renderConfigurationDetails(viewContent, status);
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

async function loadPipeline() {
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  clearNotice();
  refresh.disabled = true;
  if (pageEyebrow) pageEyebrow.textContent = "LZA Workbench / Configuration Pipeline";
  if (pageTitle) pageTitle.textContent = "Configuration Pipeline Details";
  if (breadcrumb) breadcrumb.hidden = false;

  try {
    const status = await getConfigurationStatus();
    workspacePath.textContent = status.workspace.directory;
    workspacePath.title = status.workspace.directory;
    renderPipelineDetails(viewContent, status);
    if (!status.workspace.isLive) {
      showNotice(getOfflineWarning(status.workspace.error), "warning");
    } else {
      clearNotice();
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

function handleRoute() {
  const route = parseRoute();
  if (route === "installer") {
    loadInstaller();
  } else if (route === "configuration") {
    loadConfiguration();
  } else if (route === "configuration-pipeline") {
    loadPipeline();
  } else {
    loadOverview();
  }
}

refresh.addEventListener("click", handleRoute);
window.addEventListener("hashchange", handleRoute);
handleRoute();
