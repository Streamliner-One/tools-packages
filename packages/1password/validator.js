/**
 * 1Password Validator - Uses Service Account Token
 */

const { execFile } = require('child_process');
const util = require('util');
const execFilePromise = util.promisify(execFile);

async function validate(fields) {
  const token = fields.serviceAccountToken?.value;
  
  if (!token) {
    return {
      valid: false,
      message: 'Service Account Token required'
    };
  }
  
  // Validate token format
  if (!token.startsWith('ops_')) {
    return {
      valid: false,
      message: 'Invalid token format. Should start with ops_'
    };
  }
  
  try {
    // Test with service account token (no shell dependency)
    const { stdout } = await execFilePromise('op', ['vault', 'list', '--format', 'json'], {
      env: {
        ...process.env,
        OP_SERVICE_ACCOUNT_TOKEN: token,
        HOME: process.env.HOME || '/home/alex',
        PATH: process.env.PATH || '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
      }
    });
    
    const vaults = JSON.parse(stdout);
    const vaultNames = vaults.map(v => v.name).join(', ');
    
    return {
      valid: true,
      message: `✅ Connected! Access to ${vaults.length} vaults: ${vaultNames}`
    };
    
  } catch (err) {
    return {
      valid: false,
      message: 'Connection failed: ' + (err.stderr || err.message)
    };
  }
}

module.exports = { validate };