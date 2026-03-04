/**
 * Public Holidays validator (Nager.Date)
 */

async function validate(fields) {
  try {
    const country = (fields.defaultCountry?.value || 'ES').toUpperCase();
    const year = new Date().getFullYear();
    const url = `https://date.nager.at/api/v3/publicholidays/${year}/${country}`;

    const res = await fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json', 'User-Agent': 'OpenClaw-Tools-Config/1.0' }
    });

    if (res.ok) {
      const data = await res.json();
      const count = Array.isArray(data) ? data.length : 0;
      return { valid: true, message: `Connected to Nager.Date (${country}) • ${count} holidays in ${year}` };
    }

    if (res.status === 404) {
      return { valid: false, message: `Country code not supported: ${country}` };
    }

    return { valid: false, message: `Nager.Date error: HTTP ${res.status}` };
  } catch (err) {
    return { valid: false, message: `Connection failed: ${err.message}` };
  }
}

module.exports = { validate };
