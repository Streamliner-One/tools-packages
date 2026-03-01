# Streamliner One Tools Packages

Connector catalog for Tools Config Server.

## Purpose
Stores reusable package definitions and validators for external integrations.

Examples:
- GitHub
- Stripe
- Notion
- 1Password
- Pinecone

## Structure
Each package lives in its own folder and contains:
- `package.json` (metadata + fields)
- `validator.js` (optional)

## Compatibility
Packages are versioned and designed to be consumed by `tools-config-server`.
