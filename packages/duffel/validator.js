module.exports = async function validate(fields) {
  const apiKey = fields.apiKey?.value || fields.apiKey;
  if (!apiKey) return { valid: false, message: 'API Key is required' };
  if (!apiKey.startsWith('duffel_test_') && !apiKey.startsWith('duffel_live_')) {
    return { valid: false, message: 'Unexpected Duffel key prefix' };
  }
  try {
    const res = await fetch('https://api.duffel.com/air/airlines?limit=1', {
      headers: { Authorization: `Bearer ${apiKey}`, 'Duffel-Version': 'v2' }
    });
    if (!res.ok) return { valid: false, message: `Duffel auth failed: ${res.status}` };
    const env = apiKey.startsWith('duffel_live_') ? 'live' : 'sandbox';
    return { valid: true, message: `Connected to Duffel (${env})` };
  } catch (err) {
    return { valid: false, message: err.message };
  }
};
