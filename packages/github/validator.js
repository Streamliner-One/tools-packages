/**
 * GitHub Validator - reliable backend PAT check
 */

async function validate(fields) {
  const token = fields.token?.value;

  if (!token) {
    return { valid: false, message: 'Personal Access Token required' };
  }

  if (!token.startsWith('ghp_') && !token.startsWith('github_pat_')) {
    return { valid: false, message: 'Invalid token format. Should start with ghp_ or github_pat_' };
  }

  try {
    const res = await fetch('https://api.github.com/user', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'OpenClaw-Tools-Config/1.0'
      }
    });

    if (res.ok) {
      const data = await res.json();
      const scopes = res.headers.get('x-oauth-scopes') || 'unknown';
      return { valid: true, message: `Connected as @${data.login} • scopes: ${scopes}` };
    }

    if (res.status === 401) return { valid: false, message: 'Invalid or expired token (401)' };
    if (res.status === 403) return { valid: false, message: 'Token exists but forbidden (403)' };
    return { valid: false, message: `GitHub API error: ${res.status}` };
  } catch (err) {
    return { valid: false, message: `Connection failed: ${err.message}` };
  }
}

module.exports = { validate };
