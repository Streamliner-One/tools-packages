/**
 * Readwise credential validator
 *
 * Validates the token by calling: GET https://readwise.io/api/v2/auth/
 * Header: Authorization: Token <token>
 */

function valueOf(raw) {
  if (raw && typeof raw === 'object' && 'value' in raw) return raw.value;
  return raw;
}

async function validate(fields) {
  const token = String(valueOf(fields?.apiToken) || '').trim();
  const baseUrlRaw = String(valueOf(fields?.baseUrl) || 'https://readwise.io').trim();
  const baseUrl = baseUrlRaw.replace(/\/$/, '');

  if (!token) return { valid: false, message: 'Access Token required' };

  let u;
  try {
    u = new URL(baseUrl);
  } catch {
    return { valid: false, message: 'Invalid baseUrl' };
  }

  const url = `${u.origin}/api/v2/auth/`;

  try {
    const res = await fetch(url, {
      method: 'GET',
      headers: {
        Authorization: `Token ${token}`
      }
    });

    // Readwise typically responds 204 No Content on success, but accept 200 too.
    if (res.status === 204 || res.status === 200) {
      return { valid: true, message: 'Readwise token OK' };
    }

    if (res.status === 401) {
      return { valid: false, message: 'Invalid or expired token (401)' };
    }

    if (res.status === 403) {
      return { valid: false, message: 'Token forbidden (403)' };
    }

    const text = await res.text().catch(() => '');
    return {
      valid: false,
      message: `Readwise API error: HTTP ${res.status}${text ? ` — ${text.slice(0, 140)}` : ''}`
    };
  } catch (err) {
    return { valid: false, message: `Connection failed: ${err.message}` };
  }
}

module.exports = { validate };
