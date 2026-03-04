# Streamliner One — Tools Packages

[![Org](https://img.shields.io/badge/org-Streamliner--One-181717?logo=github)](https://github.com/Streamliner-One) [![Type](https://img.shields.io/badge/type-catalog-purple)](https://github.com/Streamliner-One/tools-packages) [![Status](https://img.shields.io/badge/status-active-brightgreen)](https://github.com/Streamliner-One/tools-packages)

**Community integration packages for [tools-config-server](https://github.com/Streamliner-One/tools-config-server).**

Each package adds a new service to your credential dashboard — with field definitions, live validation, and ready-to-run API examples. Drop a folder in, restart the server, and your new integration appears instantly.

---

## Available packages

| Package | Category | Description |
|---------|----------|-------------|
| `1password` | Security | Service account for CLI access to 1Password vaults |
| `github` | Dev | GitHub API — repos, issues, PRs, workflows |
| `holidays` | Data | Public holiday calendar by country (Nager.Date, no API key) |
| `notion-enhanced` | Productivity | Notion with unlimited custom database connections |
| `resend` | Comms | Email API for developers — simple, reliable delivery |
| `stripe` | Payments | Stripe payment processing, billing, and webhooks |
| `supabase` | Database | PostgreSQL with realtime subscriptions and auth |

→ The server ships with 30+ built-in integrations. These packages extend it further.

---

## How packages work

Each package is a folder with:

```
packages/my-service/
├── package.json    ← required: schema, fields, metadata
└── validator.js    ← optional: live validation logic
```

When the server starts, it scans the `packages/` directory and merges any found packages into the service catalog. They appear in the dashboard, health checks, TOOLS.md generator, and REST API automatically.

---

## package.json schema

```json
{
  "id": "my-service",
  "name": "My Service",
  "version": "1.0.0",
  "description": "Short description shown in the dashboard",
  "icon": "🔧",
  "category": "productivity",
  "labels": ["productivity", "automation"],
  "author": "Your Name",
  "website": "https://my-service.com",
  "minServerVersion": "0.6.0",
  "fields": {
    "apiKey": {
      "label": "API Key",
      "type": "password",
      "required": true,
      "sensitive": true,
      "placeholder": "sk-...",
      "help": "Find this in your account settings"
    },
    "region": {
      "label": "Region",
      "type": "select",
      "required": false,
      "options": ["us-east-1", "eu-west-1"],
      "default": "us-east-1"
    }
  },
  "example": {
    "title": "List resources",
    "method": "GET",
    "url": "https://api.my-service.com/v1/resources",
    "headers": {
      "Authorization": "Bearer {{apiKey}}"
    }
  }
}
```

### Field types

| Type | Description |
|------|-------------|
| `password` | Sensitive — masked in UI, redacted from API responses |
| `text` | Plain string input |
| `select` | Dropdown with predefined options |
| `textarea` | Multi-line text |
| `checkbox` | Boolean toggle |

---

## validator.js (optional)

Export an async function that receives the resolved field values and returns `{ valid: boolean, message: string }`:

```js
module.exports = async function validate(fields) {
  const apiKey = fields.apiKey?.value;
  if (!apiKey) return { valid: false, message: 'API Key is required' };

  try {
    const res = await fetch('https://api.my-service.com/v1/me', {
      headers: { Authorization: `Bearer ${apiKey}` }
    });
    if (!res.ok) return { valid: false, message: `Auth failed: ${res.status}` };
    const data = await res.json();
    return { valid: true, message: `Connected as ${data.name}` };
  } catch (err) {
    return { valid: false, message: err.message };
  }
};
```

The health dashboard calls this validator on demand and shows the result on each credential card.

---

## Installing a package

### From this repo

```bash
# Copy the package into your server's packages directory
cp -r stripe ~/.openclaw/workspace/tools-server/packages/
# Restart the server — it appears automatically
```

### From the server UI

Drag-and-drop package install is coming in a future release.

---

## Contributing

1. Fork this repo
2. Create your package folder under a branch
3. Open a PR with a short description of what the service does

**Good packages have:**
- A working validator (even a simple connectivity check)
- A useful `example` block so users can test their key from the UI
- Clear field labels and help text
- Sensitive fields marked `"sensitive": true`

---

## Related

- [tools-config-server](https://github.com/Streamliner-One/tools-config-server) — the server that loads these packages
- [install](https://github.com/Streamliner-One/install) — one-line installer: `curl https://install.streamliner.one | bash`
- [streamliner.one](https://streamliner.one) — Streamliner One

---

Built by [Streamliner One](https://streamliner.one) · MIT License
