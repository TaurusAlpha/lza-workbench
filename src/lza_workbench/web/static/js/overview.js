function value(value, fallback = "Not available") {
  const text = value === null || value === undefined || value === "" ? fallback : String(value);
  return text.replace(/[&<>"']/g, (character) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
  });
}

function card(title, fields, status) {
  const rows = fields
    .filter(([, fieldValue]) => fieldValue !== undefined)
    .map(([label, fieldValue]) => `<dt>${label}</dt><dd>${value(fieldValue)}</dd>`)
    .join("");
  const badge = status ? `<span class="status">${value(status)}</span>` : "";
  return `<article class="card"><div class="card-title"><h2>${title}</h2>${badge}</div><dl>${rows}</dl></article>`;
}

function pipelineFields(pipeline) {
  return [
    ["Pipeline", pipeline.name],
    ["Latest execution", pipeline.status],
    ["Current work", [pipeline.currentStage, pipeline.currentAction].filter(Boolean).join(" / ")],
    ["Failure", pipeline.failureSummary],
  ];
}

function configurationSyncStatus(configuration) {
  if (!configuration.localGitClean) {
    return "Local changes";
  }

  switch (configuration.gitSync?.status) {
    case "Synchronized":
      return "In sync";
    case "Ahead":
    case "Behind":
    case "Diverged":
      return "Drift detected";
    case undefined:
      return "Sync unavailable";
    default:
      return configuration.gitSync.status;
  }
}

export function renderOverview(container, status) {
  container.innerHTML = [
    card("Workspace", [
      ["Customer", status.workspace.customerName],
      ["LZA version", status.workspace.lzaVersion],
      ["Directory", status.workspace.directory],
      ["Validation", "Not implemented yet"],
    ], "Validation pending"),
    card("AWS context", [
      ["Profile", status.aws.profile],
      ["Region", status.aws.region],
      ["Account", status.aws.identity?.account],
      ["Identity", status.aws.identity?.arn],
    ], status.aws.isLive ? "Live" : "Offline"),
    card("Installer", [
      ["Stack", status.installer.name],
      ["Stack status", status.installer.status],
      ["Deployed version", status.installer.deployedVersion],
    ], status.health.installer),
    card("Configuration", [
      ["Repository", `${status.configuration.repositoryType} / ${value(status.configuration.target)}`],
      ["Local Git", status.configuration.localGitBranch],
      ["Uncommitted changes", status.configuration.localGitUncommitted],
      ["Remote sync", status.configuration.gitSync?.summary],
    ], configurationSyncStatus(status.configuration)),
    card("Installer pipeline", pipelineFields(status.installerPipeline), status.installerPipeline.status),
    card("Configuration pipeline", pipelineFields(status.configurationPipeline), status.configurationPipeline.status),
  ].join("");
}
