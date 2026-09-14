/**
 * Local storage manager for recent workspaces.
 */

const STORAGE_KEY = "lza_recent_workspaces";
const MAX_RECENTS = 10;

/**
 * @typedef {Object} RecentWorkspace
 * @property {string} customerName
 * @property {string} workspaceDir
 * @property {string} [lzaVersion]
 * @property {number} lastOpenedAt
 */

/**
 * Retrieve recent workspaces sorted by most recently opened.
 * @returns {RecentWorkspace[]}
 */
export function getRecentWorkspaces() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    if (!Array.isArray(list)) return [];
    return list.sort((a, b) => (b.lastOpenedAt || 0) - (a.lastOpenedAt || 0));
  } catch (e) {
    console.warn("Failed to read recent workspaces from localStorage:", e);
    return [];
  }
}

/**
 * Record or update a workspace in recent history.
 * @param {Object} ws
 * @param {string} [ws.customerName]
 * @param {string} ws.workspaceDir
 * @param {string} [ws.lzaVersion]
 */
export function recordRecentWorkspace({ customerName, workspaceDir, lzaVersion }) {
  if (!workspaceDir) return;
  try {
    const cleanDir = workspaceDir.trim();
    const existing = getRecentWorkspaces();
    const filtered = existing.filter((item) => item.workspaceDir !== cleanDir);

    const updated = {
      customerName: customerName || "Unknown Customer",
      workspaceDir: cleanDir,
      lzaVersion: lzaVersion || "v1.15.5",
      lastOpenedAt: Date.now(),
    };

    const nextList = [updated, ...filtered].slice(0, MAX_RECENTS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(nextList));
  } catch (e) {
    console.warn("Failed to record recent workspace:", e);
  }
}

/**
 * Remove a specific workspace directory from recents.
 * @param {string} workspaceDir
 */
export function removeRecentWorkspace(workspaceDir) {
  if (!workspaceDir) return;
  try {
    const existing = getRecentWorkspaces();
    const filtered = existing.filter((item) => item.workspaceDir !== workspaceDir);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (e) {
    console.warn("Failed to remove recent workspace:", e);
  }
}

/**
 * Clear all recent workspaces.
 */
export function clearRecentWorkspaces() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (e) {
    console.warn("Failed to clear recent workspaces:", e);
  }
}
