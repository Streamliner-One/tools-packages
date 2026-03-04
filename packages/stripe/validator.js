/**
 * Stripe Custom Validator
 * Runs in sandboxed environment
 */

async function validate(fields) {
  const rawSecretKey = fields?.secretKey;
  const rawMode = fields?.mode;
  const secretKey = (rawSecretKey && typeof rawSecretKey === 'object') ? rawSecretKey.value : rawSecretKey;
  const mode = (rawMode && typeof rawMode === 'object') ? rawMode.value : rawMode;

  if (!secretKey || typeof secretKey !== 'string') {
    return { valid: false, message: 'Missing Stripe secret key' };
  }
  
  // Validate key format
  if (!secretKey.startsWith('sk_')) {
    return {
      valid: false,
      message: 'Invalid key format. Should start with sk_live_ or sk_test_'
    };
  }
  
  // Check mode consistency
  const keyMode = secretKey.includes('_live_') ? 'live' : 'test';
  if (keyMode !== mode) {
    return {
      valid: false,
      message: `Warning: Key is ${keyMode} mode but config is set to ${mode}`
    };
  }
  
  // Test API call
  try {
    const response = await fetch('https://api.stripe.com/v1/account', {
      headers: {
        'Authorization': `Bearer ${secretKey}`
      }
    });
    
    if (response.status === 200) {
      const account = await response.json();
      return {
        valid: true,
        message: `Connected: ${account.settings?.dashboard?.display_name || account.id} (${keyMode} mode)`
      };
    }
    
    if (response.status === 401) {
      return { valid: false, message: 'Invalid API key' };
    }
    
    return { valid: false, message: `Stripe API error: ${response.status}` };
  } catch (err) {
    return { valid: false, message: `Connection failed: ${err.message}` };
  }
}

module.exports = { validate };