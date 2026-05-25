module.exports = async function validate(fields) {
  const clientId = fields.clientId?.value || fields.clientId;
  const clientSecret = fields.clientSecret?.value || fields.clientSecret;
  if (!clientId || !clientSecret) return { valid: false, message: 'Client ID and secret are required' };
  try {
    const params = new URLSearchParams({ grant_type: 'client_credentials', client_id: clientId, client_secret: clientSecret });
    const res = await fetch('https://api.amadeus.com/v1/security/oauth2/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params
    });
    if (!res.ok) return { valid: false, message: `Amadeus auth failed: ${res.status}` };
    const data = await res.json();
    return { valid: true, message: `Connected to Amadeus (${data.token_type || 'Bearer'})` };
  } catch (err) {
    return { valid: false, message: err.message };
  }
};
