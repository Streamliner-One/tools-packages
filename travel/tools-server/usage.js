const https = require('https');

function valueOf(fields, key, fallback = '') {
  return fields?.[key]?.value ?? fallback;
}

function mergeParams(paramDefs = [], input = {}) {
  const out = {};
  for (const p of paramDefs) {
    // Defaults can be either a literal value or a function evaluated at request time.
    // Functions are how time-sensitive defaults (e.g. "today + N days") stay fresh
    // without periodic package edits or server restarts.
    let dflt = p.default;
    if (typeof dflt === 'function') {
      try { dflt = dflt(); } catch { dflt = undefined; }
    }
    const v = input[p.key] ?? dflt;
    if ((v === undefined || v === null || v === '') && p.required) {
      throw new Error(`Missing required param: ${p.key}`);
    }
    out[p.key] = v;
  }
  return out;
}

function applyTemplate(str, params = {}) {
  if (typeof str !== 'string') return str;
  return str.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, k) => {
    const v = params[k];
    return v === undefined || v === null ? '' : String(v);
  });
}

// Type-aware leaf substitution for request bodies.
// String-stringify-template-parse loses type info: `body: { page_size: '{{n}}' }`
// turns 10 into "10". When the upstream API validates by type (e.g. Notion's
// page_size must be a number), this fails. By walking the body before stringify
// and substituting each {{key}} leaf with the param's declared type, integers
// stay integers, booleans stay booleans.
function substituteBodyLeaf(node, params, paramDefs) {
  if (typeof node === 'string') {
    const exact = node.match(/^\{\{\s*([a-zA-Z0-9_]+)\s*\}\}$/);
    if (exact) {
      const k = exact[1];
      const v = params[k];
      if (v === undefined || v === null) return v;
      const pdef = paramDefs.find(p => p.key === k);
      const t = pdef?.type;
      if (t === 'int' || t === 'integer' || t === 'number') return Number(v);
      if (t === 'bool' || t === 'boolean') return v === true || v === 'true' || v === 1 || v === '1';
      return String(v);
    }
    return applyTemplate(node, params);
  }
  if (Array.isArray(node)) return node.map(item => substituteBodyLeaf(item, params, paramDefs));
  if (node && typeof node === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(node)) out[k] = substituteBodyLeaf(v, params, paramDefs);
    return out;
  }
  return node;
}

function renderRequest(def, inputParams = {}) {
  const params = mergeParams(def.params || [], inputParams);
  const url = applyTemplate(def.request.url, params);
  const headers = {};
  for (const [k, v] of Object.entries(def.request.headers || {})) {
    headers[k] = applyTemplate(v, params);
  }

  let body = null;
  if (def.request.body !== undefined && def.request.body !== null) {
    if (typeof def.request.body === 'string') {
      body = applyTemplate(def.request.body, params);
    } else {
      body = substituteBodyLeaf(def.request.body, params, def.params || []);
    }
  }

  const host = new URL(url).host;
  if (def.allowedHosts?.length && !def.allowedHosts.includes(host)) {
    throw new Error(`Host not allowed for this example: ${host}`);
  }

  return { params, method: def.request.method, url, headers, body };
}

function toCurl(rendered) {
  const lines = [`curl -s -X ${rendered.method} "${rendered.url}"`];
  for (const [k, v] of Object.entries(rendered.headers || {})) {
    lines.push(`  -H "${k}: ${String(v).replace(/"/g, '\\"')}"`);
  }
  if (rendered.body !== null && rendered.body !== undefined) {
    const body = typeof rendered.body === 'string' ? rendered.body : JSON.stringify(rendered.body);
    lines.push(`  -d '${body.replace(/'/g, "'\\''")}'`);
  }
  return lines.join(' \\\n');
}

async function runRenderedRequest(rendered, timeoutMs = 60000) {
  const u = new URL(rendered.url);
  const bodyStr = rendered.body == null
    ? null
    : (typeof rendered.body === 'string' ? rendered.body : JSON.stringify(rendered.body));

  const options = {
    method: rendered.method,
    hostname: u.hostname,
    port: u.port || 443,
    path: `${u.pathname}${u.search}`,
    headers: { ...(rendered.headers || {}) },
    timeout: timeoutMs
  };

  if (bodyStr != null && !options.headers['Content-Type']) {
    options.headers['Content-Type'] = 'application/json';
  }
  if (bodyStr != null) {
    options.headers['Content-Length'] = Buffer.byteLength(bodyStr);
  }

  return await new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        let parsed = null;
        try { parsed = JSON.parse(data); } catch {}
        resolve({
          status: res.statusCode,
          headers: {
            'content-type': res.headers['content-type'],
            'x-ratelimit-remaining': res.headers['x-ratelimit-remaining'],
            'x-ratelimit-reset': res.headers['x-ratelimit-reset']
          },
          body: parsed ?? data
        });
      });
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('Request timeout')));
    if (bodyStr != null) req.write(bodyStr);
    req.end();
  });
}

function getExampleDefinition(packageId, fields = {}) {
  const key    = (k, fb) => valueOf(fields, k, fb);
  const host   = (url) => { try { return new URL(url).host; } catch { return url; } };

  const defs = {

    // ── Search & Research ──────────────────────────────────────────────────
    tavily: {
      title: 'Tavily — AI web search, extract, crawl',
      summary: 'AI-optimised search, JS-capable page extraction, and recursive site crawl. /search + /extract: api_key in body. /crawl + /map: Authorization: Bearer header.',
      allowedHosts: ['api.tavily.com'],
      params: [
        { key: 'query',        type: 'string', required: true,  default: 'latest AI news' },
        { key: 'search_depth', type: 'string', required: false, default: 'basic' },
        { key: 'max_results',  type: 'int',    required: false, default: 5 }
      ],
      request: {
        method: 'POST',
        url: 'https://api.tavily.com/search',
        headers: { 'Content-Type': 'application/json' },
        body: {
          api_key: key('apiKey'),
          query: '{{query}}',
          search_depth: '{{search_depth}}',
          max_results: '{{max_results}}'
        }
      },
      expected: 'JSON with results[].title, results[].url, results[].content, results[].score',
      commonError: '401 invalid api_key (format: tvly-xxxx); 429 rate limit — free: 1000 credits/month, 1 per basic search, 2 per advanced',
      docs: 'https://docs.tavily.com/documentation/api-reference/introduction',
      additionalCalls: [
        {
          label: 'Extract — get clean content from a URL (bypasses JS/bot blocks)',
          curl: `curl -s -X POST "https://api.tavily.com/extract" \\\n  -H "Content-Type: application/json" \\\n  -d '{"api_key":"***redacted***","urls":"https://example.com","query":"optional reranking hint"}'`,
          params: [
            { key: 'urls',  type: 'string or array', required: true,  default: 'https://example.com' },
            { key: 'query', type: 'string',           required: false, default: '' }
          ],
          expected: 'JSON with results[].url, results[].raw_content, results[].images',
          commonError: '1 credit per URL; use when web_fetch fails on JS-heavy or bot-protected pages'
        },
        {
          label: 'Crawl — recursively traverse a site and extract all pages',
          curl: `curl -s -X POST "https://api.tavily.com/crawl" \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ***redacted***" \\\n  -d '{"url":"https://docs.example.com","instructions":"Find all pages about pricing","max_depth":2,"limit":20}'`,
          params: [
            { key: 'url',          type: 'string', required: true,  default: 'https://docs.example.com' },
            { key: 'instructions', type: 'string', required: false, default: '' },
            { key: 'max_depth',    type: 'int',    required: false, default: 2 },
            { key: 'limit',        type: 'int',    required: false, default: 20 }
          ],
          expected: 'JSON with results[].url, results[].raw_content — 1 credit per 10 pages (2 if instructions used)',
          commonError: 'IMPORTANT: /crawl uses Authorization: Bearer header (NOT api_key in body like /search and /extract). Pure client-side SPAs return empty results — nothing to do.'
        }
      ]
    },

    brave: {
      title: 'Brave Web Search',
      summary: 'Search the web.',
      allowedHosts: ['api.search.brave.com'],
      params: [
        { key: 'q',     type: 'string', required: true,  default: 'latest AI news' },
        { key: 'count', type: 'int',    required: false, default: 5 }
      ],
      request: {
        method: 'GET',
        url: 'https://api.search.brave.com/res/v1/web/search?q={{q}}&count={{count}}',
        headers: { 'Accept': 'application/json', 'X-Subscription-Token': key('apiKey') }
      },
      expected: 'JSON with web.results[]',
      commonError: '429 rate limit',
      docs: 'https://api.search.brave.com/app/documentation/web-search/get-started'
    },

    perplexity: {
      title: 'Perplexity AI Search',
      summary: 'AI-powered research query.',
      allowedHosts: ['api.perplexity.ai'],
      params: [
        { key: 'query', type: 'string', required: true, default: 'latest developments in AI' }
      ],
      request: {
        method: 'POST',
        url: 'https://api.perplexity.ai/chat/completions',
        headers: {
          'Authorization': `Bearer ${key('apiKey')}`,
          'Content-Type': 'application/json'
        },
        body: {
          model: 'sonar',
          messages: [{ role: 'user', content: '{{query}}' }]
        }
      },
      expected: 'JSON with choices[0].message.content',
      commonError: '401 invalid key',
      docs: 'https://docs.perplexity.ai'
    },

    newsapi: {
      title: 'NewsAPI Headlines',
      summary: 'Fetch latest news headlines. Note: /v2/top-headlines does not accept the "language" param (use country/category/sources/q); language is only valid on /v2/everything.',
      allowedHosts: ['newsapi.org'],
      params: [
        { key: 'q',        type: 'string', required: false, default: 'technology' },
        { key: 'pageSize', type: 'int',    required: false, default: 5 }
      ],
      request: {
        method: 'GET',
        url: `https://newsapi.org/v2/top-headlines?q={{q}}&pageSize={{pageSize}}&apiKey=${key('apiKey')}`,
        headers: { 'User-Agent': 'OpenClaw-Tools-Server/1.0' }
      },
      expected: 'JSON with articles[]',
      commonError: '401 invalid key; 426 developer plan only allows /top-headlines',
      docs: 'https://newsapi.org/docs'
    },

    // ── Productivity ───────────────────────────────────────────────────────
    notion: {
      title: 'Notion — query a database',
      summary: 'Query a Notion database. Default targets dbTodos (a real database in the credential fields). dbHome is a page, not a database — do not use it for query. To target dbSupplements or any other DB, pass database_id explicitly.',
      allowedHosts: ['api.notion.com'],
      params: [
        // Default reads dbTodos from the credential's fields at request time.
        // Note: dbHome is a *page* ID (Notion returns "Provided ID is a page,
        // not a database"), so it cannot be used here. dbTodos and dbSupplements
        // are real databases.
        { key: 'database_id', type: 'string', required: true, default: key('dbTodos', 'YOUR_DB_ID') },
        { key: 'page_size',   type: 'int',    required: false, default: 10 }
      ],
      request: {
        method: 'POST',
        url: 'https://api.notion.com/v1/databases/{{database_id}}/query',
        headers: {
          'Authorization': `Bearer ${key('apiKey')}`,
          // 2022-06-28 is the stable version that retains /v1/databases/{id}/query.
          // 2025-09-03 deprecated this endpoint in favor of /v1/data_sources/{id}/query
          // (which uses different data-source IDs, not database IDs).
          'Notion-Version': '2022-06-28',
          'Content-Type': 'application/json'
        },
        body: { page_size: '{{page_size}}' }
      },
      expected: 'JSON with results[] pages',
      commonError: '400 invalid_request_url (Notion-Version 2025+ deprecated this endpoint, use 2022-06-28); 400 "is a page, not a database" (use a real database ID like dbTodos or dbSupplements); 401 token not shared with integration',
      docs: 'https://developers.notion.com/reference/post-database-query'
    },

    todoist: {
      title: 'Todoist — list active tasks',
      summary: 'Fetch all active tasks.',
      allowedHosts: ['api.todoist.com'],
      params: [
        { key: 'filter', type: 'string', required: false, default: 'today | overdue' }
      ],
      request: {
        method: 'GET',
        url: 'https://api.todoist.com/api/v1/tasks?filter={{filter}}',
        headers: { 'Authorization': `Bearer ${key('apiToken')}` }
      },
      expected: 'JSON array of task objects',
      commonError: '401 invalid token; 410 if using /rest/v2/ (deprecated — use /api/v1/)',
      docs: 'https://developer.todoist.com/rest/v2/'
    },

    // ── Communication ──────────────────────────────────────────────────────
    elevenlabs: {
      title: 'ElevenLabs — list voices',
      summary: 'Verify API access and list available voices.',
      allowedHosts: ['api.elevenlabs.io'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.elevenlabs.io/v1/voices',
        headers: { 'xi-api-key': key('apiKey') }
      },
      expected: 'JSON with voices[]',
      commonError: '401 invalid key',
      docs: 'https://elevenlabs.io/docs/api-reference/get-voices'
    },

    vapi: {
      title: 'VAPI — list assistants',
      summary: 'List configured VAPI assistants.',
      allowedHosts: ['api.vapi.ai'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.vapi.ai/assistant',
        headers: { 'Authorization': `Bearer ${key('apiKey')}` }
      },
      expected: 'JSON array of assistant objects',
      commonError: '401 invalid key',
      docs: 'https://docs.vapi.ai'
    },

    // ── Travel ─────────────────────────────────────────────────────────────
    amadeus: {
      title: 'Amadeus — flight offers',
      summary: 'Search one-way flight offers. OAuth handled automatically — GET /api/credentials/amadeus returns a live bearer token as primaryKey.',
      allowedHosts: ['api.amadeus.com'],
      params: [
        { key: 'origin',         type: 'string', required: true,  default: 'VLC' },
        { key: 'destination',    type: 'string', required: true,  default: 'DXB' },
        // Dynamic default: today + 14 days, recomputed on each request so the
        // smoke test never trips on "Date is in the past" without static drift.
        { key: 'departureDate',  type: 'date',   required: true,
          default: () => new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10) },
        { key: 'adults',         type: 'int',    required: false, default: 1 }
      ],
      request: {
        method: 'GET',
        url: 'https://api.amadeus.com/v2/shopping/flight-offers?originLocationCode={{origin}}&destinationLocationCode={{destination}}&departureDate={{departureDate}}&adults={{adults}}&max=5',
        headers: { 'Authorization': 'Bearer OAUTH_AUTO_TOKEN' }
      },
      expected: 'JSON with data[] flight offers',
      commonError: '401 token expired — re-fetch primaryKey from /api/credentials/amadeus (auto-refreshes)',
      docs: 'https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search'
    },

    osrm: {
      title: 'OSRM — driving distance & duration',
      summary: 'Calculate driving distance and duration between two points. Free, no API key. Coords in lng,lat order.',
      allowedHosts: ['router.project-osrm.org'],
      params: [
        { key: 'origin',      type: 'string', required: true,  default: '7.4246,43.7384',  hint: 'lng,lat of origin (e.g. Monaco)' },
        { key: 'destination', type: 'string', required: true,  default: '11.3426,44.4949', hint: 'lng,lat of destination (e.g. Bologna)' }
      ],
      request: {
        method: 'GET',
        url: 'http://router.project-osrm.org/route/v1/driving/{{origin}};{{destination}}?overview=false',
        headers: {}
      },
      expected: 'JSON with routes[0].distance (meters), routes[0].duration (seconds). Divide by 1000/3600 for km/hours.',
      commonError: 'No failures expected — no auth. Use lng,lat order (NOT lat,lng). Public server may rate-limit heavy usage.',
      docs: 'https://project-osrm.org/docs/v5.24.0/api/'
    },

    aviationstack: {
      title: 'Aviationstack — flight status',
      summary: 'Get real-time flight status by flight number.',
      allowedHosts: ['api.aviationstack.com'],
      params: [
        { key: 'flight_iata', type: 'string', required: true, default: 'EK90' }
      ],
      request: {
        method: 'GET',
        url: `http://api.aviationstack.com/v1/flights?access_key=${key('apiKey')}&flight_iata={{flight_iata}}`,
        headers: {}
      },
      expected: 'JSON with data[] flight status objects',
      commonError: '101 invalid key; note: uses http not https on free plan',
      docs: 'https://aviationstack.com/documentation'
    },

    duffel: {
      title: 'Duffel — Flight Search & Booking',
      summary: 'Primary flight search and booking tool. Use Python client (duffel_client_v2.py), not raw curl. Live key for real lookups; sandbox key for testing. Hotels: use Amadeus instead.',
      allowedHosts: ['api.duffel.com'],
      useWhen: 'flight search, find flights, book flight, rates for route, find me flights, look me the rates, search flights',
      params: [
        { key: 'origin',         type: 'string', required: true,  default: 'VLC' },
        { key: 'destination',    type: 'string', required: true,  default: 'DXB' },
        { key: 'departureDate',  type: 'date',   required: true,  default: '2026-05-01' },
        { key: 'adults',         type: 'int',    required: false, default: 1 },
        { key: 'cabinClass',     type: 'string', required: false, default: 'economy' }
      ],
      request: {
        method: 'POST',
        url: 'https://api.duffel.com/air/offer_requests',
        headers: {
          'Authorization': `Bearer ${key('apiKey')}`,
          'Duffel-Version': 'v2',
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: {
          data: {
            slices: [{ origin: 'VLC', destination: 'DXB', departure_date: '2026-05-01' }],
            passengers: [{ type: 'adult' }],
            cabin_class: 'economy'
          }
        }
      },
      expected: 'JSON with data.offers[] — each offer has total_amount, total_currency, slices (segments), airline, stops',
      commonError: '401 invalid key. No offers = airline inactive in dashboard (EK, LX require activation). Fallback to Amadeus.',
      note: 'AGENT: Mandatory first step — read ~/.openclaw/workspace/duffel/HANDBOOK.md before answering any Duffel, flight search, fare display, booking, or offer-detail request. Then use the Python client — cd ~/.openclaw/workspace/duffel && python3 duffel_client_v2.py search <ORIGIN> <DEST> <DATE> [--cabin business] [--return-date DATE]. Follow the canonical search → list → show/expand → book workflow from the handbook. Use duffel_client_v2.py as the canonical command surface. Direct flights first, but never direct-only. Apply 3% markup for client quotes. Do not improvise alternate flight presentation formats when the handbook exists.',
      docs: 'https://duffel.com/docs/api/overview/welcome'
    },

    // ── Location & Places ──────────────────────────────────────────────────
    goplaces: {
      title: 'Google Places — text search',
      summary: 'Find places by text query.',
      allowedHosts: ['places.googleapis.com'],
      params: [
        { key: 'textQuery',       type: 'string', required: true,  default: 'best ramen Valencia Spain' },
        { key: 'maxResultCount',  type: 'int',    required: false, default: 3 }
      ],
      request: {
        method: 'POST',
        url: 'https://places.googleapis.com/v1/places:searchText',
        headers: {
          'Content-Type': 'application/json',
          'X-Goog-Api-Key': key('apiKey'),
          'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.rating,places.priceLevel'
        },
        body: { textQuery: '{{textQuery}}', maxResultCount: '{{maxResultCount}}' }
      },
      expected: 'JSON with places[]',
      commonError: '403 API key restricted or Places API not enabled',
      docs: 'https://developers.google.com/maps/documentation/places/web-service/text-search'
    },

    // ── Finance ────────────────────────────────────────────────────────────
    openexchangerates: {
      title: 'Open Exchange Rates — latest rates',
      summary: 'Get current exchange rates against USD.',
      allowedHosts: ['openexchangerates.org'],
      params: [
        { key: 'symbols', type: 'string', required: false, default: 'EUR,CHF,AED,GBP' }
      ],
      request: {
        method: 'GET',
        url: `https://openexchangerates.org/api/latest.json?app_id=${key('apiKey')}&symbols={{symbols}}`,
        headers: {}
      },
      expected: 'JSON with rates{} object',
      commonError: '401 invalid key; 429 rate limit on free plan',
      docs: 'https://docs.openexchangerates.org/reference/api-introduction'
    },

    stripe: {
      title: 'Stripe — account balance',
      summary: '⚠️ TEST MODE — check account balance.',
      allowedHosts: ['api.stripe.com'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.stripe.com/v1/balance',
        headers: { 'Authorization': `Bearer ${key('secretKey')}` }
      },
      expected: 'JSON with available[] and pending[] balance objects',
      commonError: '401 invalid key; ensure using test key (sk_test_...)',
      docs: 'https://stripe.com/docs/api/balance/balance_retrieve'
    },

    // ── Health ─────────────────────────────────────────────────────────────
    oura: {
      title: 'Oura — via n8n workflow',
      summary: 'Oura OAuth is managed by n8n. Trigger the health check workflow.',
      allowedHosts: [host(key('hostUrl', 'https://n8n.streamliner.one'))],
      params: [],
      request: {
        method: 'GET',
        url: `${key('hostUrl', 'https://n8n.streamliner.one')}/api/v1/workflows`,
        headers: { 'X-N8N-API-KEY': key('apiKey') }
      },
      expected: 'JSON listing workflows including Oura ones',
      commonError: '401 invalid n8n key',
      docs: 'https://docs.n8n.io/api/'
    },

    // ── AI Models ──────────────────────────────────────────────────────────
    openai: {
      title: 'OpenAI — list models',
      summary: 'Verify API access.',
      allowedHosts: ['api.openai.com'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.openai.com/v1/models',
        headers: { 'Authorization': `Bearer ${key('apiKey')}` }
      },
      expected: 'JSON with data[] models',
      commonError: '401 invalid key',
      docs: 'https://platform.openai.com/docs/api-reference/models'
    },

    anthropic: {
      title: 'Anthropic — list models',
      summary: 'Verify API access.',
      allowedHosts: ['api.anthropic.com'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.anthropic.com/v1/models',
        headers: {
          'x-api-key': key('apiKey'),
          'anthropic-version': '2023-06-01'
        }
      },
      expected: 'JSON with data[] models',
      commonError: '401 invalid key',
      docs: 'https://docs.anthropic.com/en/api/models-list'
    },

    moonshot: {
      title: 'Moonshot (Kimi) — list models',
      summary: 'Verify API access. Use the .ai (international) endpoint to match the validator; the .cn endpoint is a separate geo and does not accept .ai-issued keys.',
      allowedHosts: ['api.moonshot.ai'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.moonshot.ai/v1/models',
        headers: { 'Authorization': `Bearer ${key('apiKey')}` }
      },
      expected: 'JSON with data[] models',
      commonError: '401 invalid key (or wrong geo endpoint — .ai vs .cn use separate keyspaces)',
      docs: 'https://platform.moonshot.ai/docs'
    },

    ollama: {
      title: 'Ollama Cloud — chat completion',
      summary: 'OpenAI-compatible cloud inference. Base URL: https://ollama.com/v1 (NOT api.ollama.com — that 301s). Pro plan ($20/mo) for cloud models. No :cloud suffix needed.',
      allowedHosts: ['ollama.com'],
      params: [
        { key: 'model', type: 'string', required: true, default: 'glm-5.1' }
      ],
      request: {
        method: 'POST',
        url: 'https://ollama.com/v1/chat/completions',
        headers: {
          'Authorization': `Bearer ${key('apiKey')}`,
          'Content-Type': 'application/json'
        },
        body: {
          model: '{{model}}',
          messages: [{ role: 'user', content: 'Say hello' }],
          stream: false
        }
      },
      expected: 'JSON with choices[0].message.content',
      commonError: '301 if using api.ollama.com — correct base is ollama.com/v1; 401 invalid key; 429 session limit (resets every 5h)',
      docs: 'https://docs.ollama.com/integrations/openclaw'
    },

    google: {
      title: 'Google Gemini — list models',
      summary: 'Verify Gemini API access.',
      allowedHosts: ['generativelanguage.googleapis.com'],
      params: [],
      request: {
        method: 'GET',
        url: `https://generativelanguage.googleapis.com/v1beta/models?key=${key('apiKey')}`,
        headers: {}
      },
      expected: 'JSON with models[]',
      commonError: '400 API not enabled; 403 key restricted',
      docs: 'https://ai.google.dev/api/models'
    },

    nanoBanana: {
      title: 'Nano Banana Pro — generate image',
      summary: 'Generate an image via Gemini image model.',
      allowedHosts: ['generativelanguage.googleapis.com'],
      params: [
        { key: 'prompt', type: 'string', required: true, default: 'a serene Japanese garden at sunset' }
      ],
      request: {
        method: 'POST',
        url: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key=${key('apiKey')}`,
        headers: { 'Content-Type': 'application/json' },
        body: {
          contents: [{ parts: [{ text: '{{prompt}}' }] }],
          generationConfig: { responseModalities: ['image', 'text'] }
        }
      },
      expected: 'JSON with candidates[0].content.parts containing inlineData with image',
      commonError: '400 model not available; 403 key restricted',
      docs: 'https://ai.google.dev/gemini-api/docs/image-generation'
    },

    whisper: {
      title: 'OpenAI Whisper — transcribe audio',
      summary: 'Transcribe an audio file. Requires multipart form — use exec+curl, not this example directly.',
      allowedHosts: ['api.openai.com'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.openai.com/v1/models',
        headers: { 'Authorization': `Bearer ${key('apiKey')}` }
      },
      expected: 'Use: curl -s -X POST "https://api.openai.com/v1/audio/transcriptions" -H "Authorization: Bearer KEY" -F "file=@audio.mp3" -F "model=whisper-1"',
      commonError: '401 invalid key',
      docs: 'https://platform.openai.com/docs/api-reference/audio/createTranscription'
    },

    // ── Knowledge & Memory ─────────────────────────────────────────────────
    readwise: {
      title: 'Readwise — fetch highlights',
      summary: 'Fetch recent highlights from Readwise.',
      allowedHosts: ['readwise.io'],
      params: [
        { key: 'page_size', type: 'int',    required: false, default: 10 },
        { key: 'category',  type: 'string', required: false, default: '' }
      ],
      request: {
        method: 'GET',
        url: 'https://readwise.io/api/v2/highlights/?page_size={{page_size}}&category={{category}}',
        headers: { 'Authorization': `Token ${key('apiToken')}` }
      },
      expected: 'JSON with results[] highlights',
      commonError: '401 invalid token; note field is apiToken not apiKey',
      docs: 'https://readwise.io/api_deets'
    },

    pinecone: {
      title: 'Pinecone — index stats',
      summary: 'Check vector count and index health.',
      allowedHosts: [host(`https://${key('indexHost', 'index.pinecone.io')}`)],
      params: [],
      request: {
        method: 'POST',
        url: `https://${key('indexHost', 'index.pinecone.io')}/describe_index_stats`,
        headers: {
          'Api-Key': key('apiKey'),
          'Content-Type': 'application/json'
        },
        body: {}
      },
      expected: 'JSON with totalVectorCount and namespaces',
      commonError: '403 check API key or IP allowlist',
      docs: 'https://docs.pinecone.io/reference/api/data-plane/describeindexstats'
    },

    // ── Automation ─────────────────────────────────────────────────────────
    n8n: {
      title: 'n8n — list workflows',
      summary: 'List all n8n workflows.',
      allowedHosts: [host(key('hostUrl', 'https://n8n.example.com'))],
      params: [],
      request: {
        method: 'GET',
        url: `${key('hostUrl', 'https://n8n.example.com')}/api/v1/workflows?limit=20`,
        headers: { 'X-N8N-API-KEY': key('apiKey') }
      },
      expected: 'JSON with data[] workflows',
      commonError: '401 invalid key or wrong host',
      docs: 'https://docs.n8n.io/api/'
    },

    // ── Logistics ──────────────────────────────────────────────────────────
    '17track': {
      title: '17TRACK — register tracking',
      summary: 'Register a tracking number to start tracking.',
      allowedHosts: ['api.17track.net'],
      params: [
        { key: 'tracking_number', type: 'string', required: true, default: 'ABCD1234567890' }
      ],
      request: {
        method: 'POST',
        url: 'https://api.17track.net/track/v2.2/register',
        headers: {
          '17token': key('apiKey'),
          'Content-Type': 'application/json'
        },
        body: [{ number: '{{tracking_number}}' }]
      },
      expected: 'JSON with accepted[] and rejected[] arrays',
      commonError: '401 invalid key; note auth header is "17token" not "Authorization"',
      docs: 'https://api.17track.net/en/doc'
    },

    // ── Dev & Infrastructure ───────────────────────────────────────────────
    github: {
      title: 'GitHub — auth user',
      summary: 'Verify token and get authenticated user. GitHub requires a User-Agent header on every request.',
      allowedHosts: ['api.github.com'],
      params: [],
      request: {
        method: 'GET',
        url: 'https://api.github.com/user',
        headers: {
          'Authorization': `Bearer ${key('token')}`,
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'OpenClaw-Tools-Server/1.0'
        }
      },
      expected: 'JSON with login, name, email',
      commonError: '401 invalid token',
      docs: 'https://docs.github.com/en/rest/users/users'
    },

    '1password': {
      title: '1Password — list vaults',
      summary: 'List accessible vaults via op CLI. Not a direct API call — use op CLI.',
      allowedHosts: [],
      params: [],
      request: { method: 'GET', url: 'https://example.com', headers: {} },
      expected: 'Use: op vault list   |   op read "op://Alex-Mel/item/field"',
      commonError: 'Token expired — sync-op-token.sh handles refresh from tools server',
      docs: 'https://developer.1password.com/docs/cli'
    },

    // ── Utilities ──────────────────────────────────────────────────────────
    weather: {
      title: 'Weather — current conditions',
      summary: 'No API key needed. Uses wttr.in or Open-Meteo.',
      allowedHosts: ['wttr.in'],
      params: [
        { key: 'location', type: 'string', required: true, default: 'Valencia' }
      ],
      request: {
        method: 'GET',
        url: 'https://wttr.in/{{location}}?format=j1',
        headers: {}
      },
      expected: 'JSON with current_condition[], weather[] forecast',
      commonError: 'No failures expected — no auth required',
      docs: 'https://wttr.in/:help'
    },

    holidays: {
      title: 'Public Holidays — by country',
      summary: 'No API key needed. Uses Nager.Date.',
      allowedHosts: ['date.nager.at'],
      params: [
        { key: 'year',        type: 'int',    required: true,  default: new Date().getFullYear() },
        { key: 'countryCode', type: 'string', required: true,  default: 'ES' }
      ],
      request: {
        method: 'GET',
        url: 'https://date.nager.at/api/v3/publicholidays/{{year}}/{{countryCode}}',
        headers: {}
      },
      expected: 'JSON array of holiday objects with date, localName, name',
      commonError: 'No auth required; 404 if country code unsupported',
      docs: 'https://date.nager.at/swagger/index.html'
    },

    // ── Google Workspace ───────────────────────────────────────────────────
    'google-workspace': (() => {
      const client  = key('gogClient') || '';
      const account = key('account')   || 'unknown@example.com';
      return {
        title:       `Google Workspace — ${account}`,
        summary:     'Not a direct API call. Use gog CLI with keyring password from local file.',
        allowedHosts: [],
        params:      [],
        request:     { method: 'GET', url: 'https://example.com', headers: {} },
        expected: [
          'export GOG_KEYRING_PASSWORD=$(cat ~/.openclaw/workspace/memory/gog_keyring_password.txt)',
          `# Account: ${account}  |  client: ${client}`,
          `# ALWAYS use --client flag, NOT --account`,
          `gog gmail search "subject:invoice" --client ${client}`,
          `gog calendar list --client ${client}`,
          `gog drive list --client ${client}`,
          '',
          '# READ A FULL THREAD (correct pattern):',
          `# 1. gog gmail search "query" --client ${client}  ->  note threadId`,
          `# 2. gog gmail thread get <threadId> --client ${client} --full`,
          '# DO NOT use gog gmail get <messageId> — single message only, misses replies',
          '',
          '# SEND EMAIL:',
          `gog gmail send --client ${client} --to "recipient@example.com" --subject "Subject" --body "Body"`,
        ].join('\n'),
        commonError: `Wrong keyring password — use file, not tools server field. Use --client ${client} (NOT --account ${account}).`,
        docs: 'https://github.com/rclone/rclone'
      };
    })(),

    // ── Support & CRM ──────────────────────────────────────────────────────
    agentmail: {
      title: 'AgentMail — list messages',
      summary: 'API-native agent email. Auth: Authorization: Bearer. Inboxes: mel.miles@agentmail.to (Mel Miles), streamliner@agentmail.to (Streamliner One). Via.travel is READ-ONLY — never send from it.',
      allowedHosts: ['api.agentmail.to'],
      params: [
        { key: 'inbox_id', type: 'string', required: false, default: 'mel.miles@agentmail.to' },
        { key: 'limit',    type: 'int',    required: false, default: 10 }
      ],
      request: {
        method: 'GET',
        url: 'https://api.agentmail.to/v0/inboxes/{{inbox_id}}/messages?limit={{limit}}',
        headers: { 'Authorization': `Bearer ${key('apiKey')}` }
      },
      expected: 'JSON with messages[] array — message_id, thread_id, from, to, subject, preview, labels, timestamps',
      commonError: '401 invalid key; 403 wrong inbox (inbox_id must match your org); auth header is Authorization: Bearer not x-api-key',
      docs: 'https://docs.agentmail.to',
      additionalCalls: [
        {
          label: 'Send Message — send a new email from an AgentMail inbox',
          curl: `curl -s -X POST "https://api.agentmail.to/v0/inboxes/mel.miles@agentmail.to/messages/send" \\\n  -H "Authorization: Bearer ***redacted***" \\\n  -H "Content-Type: application/json" \\\n  -d '{"to":["recipient@example.com"],"subject":"Hello","text":"Body text"}'`,
          params: [
            { key: 'inbox_id', type: 'string',          required: true,  default: 'mel.miles@agentmail.to' },
            { key: 'to',       type: 'string or array',  required: true,  default: 'recipient@example.com' },
            { key: 'subject',  type: 'string',           required: false, default: '' },
            { key: 'text',     type: 'string',           required: false, default: '' },
            { key: 'html',     type: 'string',           required: false, default: '' },
            { key: 'cc',       type: 'string or array',  required: false, default: '' },
            { key: 'bcc',      type: 'string or array',  required: false, default: '' }
          ],
          expected: 'JSON with message_id, thread_id',
          commonError: '403 Message Rejected — check inbox_id is yours; to must be a list; do NOT send from alexey.prudkov@via.travel (read-only monitoring inbox)'
        },
        {
          label: 'Reply To Message — reply to a received email (preserves thread)',
          curl: `curl -s -X POST "https://api.agentmail.to/v0/inboxes/mel.miles@agentmail.to/messages/{{message_id}}/reply" \\\n  -H "Authorization: Bearer ***redacted***" \\\n  -H "Content-Type: application/json" \\\n  -d '{"to":["recipient@example.com"],"text":"Reply body"}'`,
          params: [
            { key: 'inbox_id',   type: 'string',         required: true,  default: 'mel.miles@agentmail.to' },
            { key: 'message_id', type: 'string',         required: true,  default: '' },
            { key: 'to',         type: 'string or array', required: true,  default: 'recipient@example.com' },
            { key: 'text',       type: 'string',         required: false, default: '' },
            { key: 'html',       type: 'string',         required: false, default: '' }
          ],
          expected: 'JSON with message_id, thread_id',
          commonError: 'to must be a list; message_id must be the ID of the original received message'
        },
        {
          label: 'Get Thread — fetch full email thread by thread_id',
          curl: `curl -s -X GET "https://api.agentmail.to/v0/threads/{{thread_id}}/messages" \\\n  -H "Authorization: Bearer ***redacted***"`,
          params: [
            { key: 'thread_id', type: 'string', required: true, default: '' }
          ],
          expected: 'JSON with messages[] array in thread order — message_id, from, to, subject, text, html, timestamps',
          commonError: '404 if thread_id not found or belongs to different org'
        }
      ]
    },

    groove: {
      title: 'Groove — list open tickets',
      summary: 'Fetch open support tickets. Base URL is configurable per client.',
      allowedHosts: ['api.groovehq.com'],
      params: [
        { key: 'status', type: 'string', required: false, default: 'open' },
        { key: 'per_page', type: 'int', required: false, default: 25 }
      ],
      request: {
        method: 'GET',
        url: `${key('baseUrl', 'https://api.groovehq.com/v1/')}tickets?status={{status}}&per_page={{per_page}}`,
        headers: { 'Authorization': `Bearer ${key('apiToken')}` }
      },
      expected: 'JSON with tickets[] array',
      commonError: '401 invalid token; auth format is Bearer <apiToken>. Ensure admin access in Groove account settings → API',
      docs: 'https://doc.groovehq.com/'
    },

    // ── Managed by OpenClaw runtime ────────────────────────────────────────
    telegram: {
      title: 'Telegram — managed by OpenClaw',
      summary: 'Use the `message` tool, not direct API calls.',
      allowedHosts: [],
      params: [],
      request: { method: 'GET', url: 'https://example.com', headers: {} },
      expected: 'Use message tool: action=send, channel=telegram',
      commonError: 'Do not call Telegram API directly',
      docs: null
    },

    mem0: {
      title: 'Mem0 — self-hosted',
      summary: 'Self-hosted on this VPS. Use memory_search / memory_store tools.',
      allowedHosts: [],
      params: [],
      request: { method: 'GET', url: 'https://example.com', headers: {} },
      expected: 'Use memory_search / memory_store / memory_list tools directly',
      commonError: 'If Qdrant or Neo4j is down, check docker ps',
      docs: null
    },

    'obsidian-sync': {
      title: 'Obsidian Sync — local vault',
      summary: 'Vault is synced locally. Read/write markdown files directly.',
      allowedHosts: [],
      params: [],
      request: { method: 'GET', url: 'https://example.com', headers: {} },
      expected: 'Read/write files in vault path from credential. Use obsidian CLI skill.',
      commonError: 'Vault out of sync — run obsidian sync manually',
      docs: null
    }
  };

  const def = defs[packageId];
  if (def) return def;

  return {
    title: `${packageId} quick query`,
    summary: 'No runnable example defined for this package yet.',
    allowedHosts: [],
    params: [],
    request: { method: 'GET', url: 'https://example.com', headers: {} },
    expected: 'Provider-specific JSON response',
    commonError: 'Auth key format or endpoint mismatch',
    docs: null
  };
}

function redactForDisplay(rendered) {
  const SENSITIVE_KEY_RE = /authorization|api.?key|api_key|token|secret|17token|xi-api|password|credential/i;

  const headers = { ...(rendered.headers || {}) };
  for (const k of Object.keys(headers)) {
    if (SENSITIVE_KEY_RE.test(k)) {
      headers[k] = '***redacted***';
    }
  }

  // Also redact sensitive fields in request body (e.g. Tavily api_key in body)
  let body = rendered.body;
  if (body && typeof body === 'object') {
    body = { ...body };
    for (const k of Object.keys(body)) {
      if (SENSITIVE_KEY_RE.test(k)) {
        body[k] = '***redacted***';
      }
    }
  }

  return { ...rendered, headers, body };
}

function buildUsageExample(packageId, fields = {}) {
  const def = getExampleDefinition(packageId, fields);
  try {
    const rendered = renderRequest(def, {});
    return {
      title: def.title,
      summary: def.summary,
      params: def.params,
      curl: toCurl(redactForDisplay(rendered)),
      expected: def.expected,
      commonError: def.commonError,
      docs: def.docs,
      additionalCalls: def.additionalCalls || []
    };
  } catch {
    return {
      title: def.title,
      summary: def.summary,
      params: def.params,
      curl: null,
      expected: def.expected,
      commonError: def.commonError,
      docs: def.docs,
      additionalCalls: def.additionalCalls || []
    };
  }
}

module.exports = {
  buildUsageExample,
  getExampleDefinition,
  renderRequest,
  toCurl,
  runRenderedRequest,
  redactForDisplay
};
