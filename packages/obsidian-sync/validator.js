/**
 * Obsidian Sync (Headless) validator
 *
 * Strategy:
 *  - Ensure `ob` CLI exists
 *  - Check login status via `ob login` (non-interactive; prints account info when logged in)
 *  - If vault path exists, attempt `ob sync-status --path <vaultPath>`
 *
 * Notes:
 *  - We intentionally do NOT run `ob sync-setup` here (mutates vault).
 *  - If not logged in / not linked, validator returns clear next-step instructions.
 */

const { spawnSync } = require('child_process');
const fs = require('fs');

function valueOf(raw) {
  if (raw && typeof raw === 'object' && 'value' in raw) return raw.value;
  return raw;
}

function run(cmd, args, opts = {}) {
  const out = spawnSync(cmd, args, {
    encoding: 'utf8',
    timeout: opts.timeoutMs ?? 15000,
    env: { ...process.env, ...(opts.env || {}) }
  });
  const stdout = (out.stdout || '').trim();
  const stderr = (out.stderr || '').trim();
  return { status: out.status, stdout, stderr, error: out.error };
}

async function validate(fields) {
  const vaultPath = String(valueOf(fields?.vaultPath) || '').trim();
  const remoteVault = String(valueOf(fields?.remoteVault) || '').trim();

  if (!vaultPath) {
    return {
      valid: false,
      message: 'Local vault path not set yet. Recommended: leave it blank and use the dashboard Login button to auto-create a safe server-managed vault directory and link it via ob sync-setup (requires remoteVault).'
    };
  }

  // 1) Resolve `ob` CLI path (tools-server may run with a restricted PATH)
  let obCmd = null;

  const explicit = process.env.OB_CLI_PATH;
  if (explicit && fs.existsSync(explicit)) obCmd = explicit;

  if (!obCmd) {
    const which = run('bash', ['-lc', 'command -v ob 2>/dev/null || true']);
    const p = (which.stdout || '').split(/\r?\n/)[0].trim();
    if (p) obCmd = p;
  }

  if (!obCmd) {
    const home = process.env.HOME || '/home/alex';
    const candidate = `${home}/.npm-global/bin/ob`;
    if (fs.existsSync(candidate)) obCmd = candidate;
  }

  if (!obCmd) {
    return {
      valid: false,
      message: 'obsidian-headless CLI not found (missing `ob`). Fix: ensure ~/.npm-global/bin is on PATH for the tools-server service, or set OB_CLI_PATH to the full path (e.g. /home/alex/.npm-global/bin/ob).'
    };
  }

  // 2) Login status
  // `ob login` may exit 0 even when it wants to prompt; the real proof is `sync-list-remote`.
  const login = run(obCmd, ['login'], { timeoutMs: 20000 });
  if (login.status !== 0) {
    return {
      valid: false,
      message: 'Obsidian Sync auth not configured on this server yet. Run: ob login (interactive)'
    };
  }

  const remote = run(obCmd, ['sync-list-remote'], { timeoutMs: 20000 });
  const remoteCombined = `${remote.stdout}\n${remote.stderr}`.trim();
  if (remote.status !== 0) {
    return {
      valid: false,
      message: 'Not logged in to Obsidian Sync on this server (cannot list remote vaults). Run: ob login (interactive)'
    };
  }

  const firstLine = remoteCombined.split(/\r?\n/).find(Boolean) || 'remote vaults listed';
  const accountHint = firstLine.slice(0, 120);

  // 3) Vault path exists?
  if (!fs.existsSync(vaultPath)) {
    return {
      valid: false,
      message: `Logged in (${accountHint}), but local vault path not found: ${vaultPath}. This path is where the remote vault is synced to disk. Fix: (a) clear vaultPath and click the dashboard Login button to auto-create a safe server-managed folder, or (b) create the directory and run ob sync-setup.`
    };
  }

  // 4) Sync configured for this vault?
  const status = run(obCmd, ['sync-status', '--path', vaultPath], { timeoutMs: 20000 });
  if (status.status === 0) {
    return {
      valid: true,
      message: `Obsidian Sync OK (${accountHint}). Vault linked: ${vaultPath}`
    };
  }

  // Not linked yet — provide next steps.
  const hint = remoteVault ? `ob sync-setup --vault "${remoteVault}" --path "${vaultPath}"` : `cd "${vaultPath}" && ob sync-list-remote && ob sync-setup --vault "<Vault Name>"`;
  return {
    valid: false,
    message: `Logged in (${accountHint}), but this vault is not linked for sync yet. Next: ${hint}`
  };
}

module.exports = { validate };
