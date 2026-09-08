import { getStatus } from "./api.js";
import { renderOverview } from "./overview.js";

const overview = document.querySelector("#overview");
const notice = document.querySelector("#notice");
const workspacePath = document.querySelector("#workspace-path");
const refresh = document.querySelector("#refresh");

async function loadStatus() {
  overview.setAttribute("aria-busy", "true");
  notice.replaceChildren();
  refresh.disabled = true;

  try {
    const status = await getStatus();
    workspacePath.textContent = status.workspace.directory;
    renderOverview(overview, status);
    if (!status.aws.isLive) {
      notice.textContent = status.aws.error ?? "AWS is unavailable; showing recorded status.";
      notice.className = "notice warning";
    }
  } catch (error) {
    workspacePath.textContent = "Workspace status unavailable";
    overview.replaceChildren();
    notice.textContent = error.message;
    notice.className = "notice error";
  } finally {
    overview.setAttribute("aria-busy", "false");
    refresh.disabled = false;
  }
}

refresh.addEventListener("click", loadStatus);
loadStatus();
