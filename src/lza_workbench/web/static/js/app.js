import { getConfigurationStatus, getStatus } from "./api.js";
import { renderConfigurationDetails } from "./configuration.js";
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
  if (clean === "/configuration") {
    return "configuration";
  }
  if (clean === "/configuration-pipeline" || clean === "/pipeline/configuration") {
    return "configuration-pipeline";
  }
  return "overview";
}

async function loadOverview() {
  viewContent.className = "card-grid";
  viewContent.setAttribute("aria-busy", "true");
  notice.replaceChildren();
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
      notice.textContent = status.aws.error ?? "AWS is unavailable; showing recorded status.";
      notice.className = "notice warning";
    }
  } catch (error) {
    workspacePath.textContent = "Workspace status unavailable";
    workspacePath.removeAttribute("title");
    viewContent.replaceChildren();
    notice.textContent = error.message;
    notice.className = "notice error";
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

async function loadConfiguration() {
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  notice.replaceChildren();
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
      notice.textContent = status.workspace.error ?? "AWS is unavailable; showing recorded status.";
      notice.className = "notice warning";
    }
  } catch (error) {
    workspacePath.textContent = "Configuration status unavailable";
    workspacePath.removeAttribute("title");
    viewContent.replaceChildren();
    notice.textContent = error.message;
    notice.className = "notice error";
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

async function loadPipeline() {
  viewContent.className = "view-container";
  viewContent.setAttribute("aria-busy", "true");
  notice.replaceChildren();
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
      notice.textContent = status.workspace.error ?? "AWS is unavailable; showing recorded status.";
      notice.className = "notice warning";
    }
  } catch (error) {
    workspacePath.textContent = "Pipeline status unavailable";
    workspacePath.removeAttribute("title");
    viewContent.replaceChildren();
    notice.textContent = error.message;
    notice.className = "notice error";
  } finally {
    viewContent.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

function handleRoute() {
  const route = parseRoute();
  if (route === "configuration") {
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
