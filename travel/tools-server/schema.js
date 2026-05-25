// Service schemas - defines the form structure for each integration

const AGENT_SCHEMA = {
  id: 'mel',
  name: 'Mel (Agent Behavior)',
  category: 'agent',
  labels: ['agent', 'ops', 'reliability'],
  icon: '✨',
  description: 'Agent behavior and rate limit settings',
  fields: [
    { 
      key: 'rateLimitNotify', 
      label: 'Notify on rate limits (429)', 
      type: 'select', 
      required: true, 
      options: ['always', 'after-3-retries', 'never'],
      default: 'always',
      help: 'When to inform user about rate limit errors'
    },
    { 
      key: 'rateLimitPauseSeconds', 
      label: 'Pause duration (seconds)', 
      type: 'number', 
      required: false, 
      placeholder: '30',
      default: '30',
      help: 'How long to pause when hitting 429 before retrying'
    },
    { 
      key: 'rateLimitMaxRetries', 
      label: 'Max retries', 
      type: 'number', 
      required: false, 
      placeholder: '3',
      default: '3',
      help: 'Maximum retry attempts with exponential backoff'
    },
    {
      key: 'rateLimitBackoffMultiplier',
      label: 'Backoff multiplier',
      type: 'number',
      required: false,
      placeholder: '2',
      default: '2',
      help: 'Multiply wait time by this factor on each retry (1.5 = conservative, 2 = standard, 3 = aggressive)'
    }
  ]
};

const SERVICE_SCHEMAS = {
  notion: {
    id: 'notion',
    name: 'Notion',
    category: 'productivity',
    labels: ['productivity', 'notes', 'database', 'knowledge'],
    icon: '📋',
    description: 'Note-taking and databases',
    skill: {
      useWhen: 'create note, add to notion, check todos, notion database, quick capture, log entry, save to notion',
      intents: ['note_create', 'todo_check', 'database_query', 'knowledge_store'],
      params: ['content', 'databaseId (optional)', 'title'],
      fallback: 'none'
    },
    dataPolicy: {
      allowedInputs: ['queries', 'dates', 'public_info', 'business_internal'],
      blockedInputs: ['passport_data', 'credentials'],
      requiresConfirmation: false,
      auditLevel: 'standard'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true, help: 'From notion.so/my-integrations' },
      { key: 'dbHome', label: 'Home DB ID', type: 'text', required: false },
      { key: 'dbTodos', label: 'Todos DB ID', type: 'text', required: false },
      { key: 'dbSupplements', label: 'Supplements DB ID', type: 'text', required: false }
    ],
    validation: {
      endpoint: 'https://api.notion.com/v1/users/me',
      headers: { 'Notion-Version': '2022-06-28' }
    },
    multiAccount: {
      supported: true,
      labelRequired: true
    }
  },

  'notion-enhanced': {
    id: 'notion-enhanced',
    name: 'Notion (Enhanced)',
    category: 'productivity',
    labels: ['productivity', 'notes', 'database', 'knowledge', 'multi-db'],
    icon: '📋',
    description: 'Notion with unlimited custom database connections',
    fields: [
      { key: 'version', label: 'Version', type: 'text', required: false },
      { key: 'db1Name', label: 'DB1 Name', type: 'text', required: false },
      { key: 'db1Id', label: 'DB1 ID', type: 'text', required: false },
      { key: 'db2Name', label: 'DB2 Name', type: 'text', required: false },
      { key: 'db2Id', label: 'DB2 ID', type: 'text', required: false },
      { key: 'db3Name', label: 'DB3 Name', type: 'text', required: false },
      { key: 'db3Id', label: 'DB3 ID', type: 'text', required: false }
    ]
  },

  todoist: {
    id: 'todoist',
    name: 'Todoist',
    category: 'productivity',
    labels: ['productivity', 'tasks', 'todo', 'planning'],
    icon: '✅',
    description: 'Task management',
    skill: {
      useWhen: 'add task, create reminder, my tasks, what\'s on my todo list, due tasks, task management',
      intents: ['task_create', 'task_list', 'task_complete'],
      params: ['taskName', 'dueDate (optional)', 'priority (optional)'],
      fallback: 'none'
    },
    dataPolicy: {
      allowedInputs: ['queries', 'dates', 'public_info'],
      blockedInputs: ['client_pii', 'passport_data', 'credentials'],
      requiresConfirmation: false,
      auditLevel: 'standard'
    },
    fields: [
      { key: 'apiToken', label: 'API Token', type: 'password', required: true, sensitive: true, help: 'From todoist.com/app/settings/integrations' }
    ],
    validation: {
      endpoint: 'https://api.todoist.com/api/v1/projects',
      source: '1password',
      item: 'Todoist API',
      field: 'credential'
    }
  },

  n8n: {
    id: 'n8n',
    name: 'n8n',
    category: 'automation',
    labels: ['automation', 'workflow', 'integration', 'orchestration'],
    icon: '⚙️',
    description: 'Workflow automation',
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true, source: '1password', item: 'n8n API', field: 'credential' },
      { key: 'hostUrl', label: 'Host URL', type: 'url', required: true, placeholder: 'https://n8n.example.com', source: '1password', item: 'n8n API', field: 'hostname' },
      { key: 'webhook17track', label: '17TRACK Webhook', type: 'url', required: false, placeholder: 'https://n8n.../webhook/17track-to-mel' }
    ]
  },

  oura: {
    id: 'oura',
    name: 'Oura',
    category: 'health',
    labels: ['health', 'sleep', 'wellness', 'biometrics'],
    icon: '💍',
    description: 'Sleep and health tracking',
    skill: {
      useWhen: 'sleep score, how did I sleep, HRV, readiness score, activity data, health stats, oura data',
      intents: ['sleep_data', 'health_metrics', 'readiness_check'],
      params: ['date (optional, defaults to today)'],
      fallback: 'none'
    },
    dataPolicy: {
      allowedInputs: ['dates', 'health_data'],
      blockedInputs: ['credentials'],
      requiresConfirmation: false,
      auditLevel: 'standard'
    },
    fields: [
      { key: 'clientId', label: 'Client ID', type: 'text', required: true, source: '1password', item: 'Oura API' },
      { key: 'clientSecret', label: 'Client Secret', type: 'password', required: true, sensitive: true, source: '1password', item: 'Oura API', field: 'credential' }
    ]
  },

  '17track': {
    id: '17track',
    name: '17TRACK',
    category: 'logistics',
    labels: ['logistics', 'tracking', 'shipping', 'ecommerce'],
    icon: '📦',
    description: 'Package tracking',
    skill: {
      useWhen: 'track package, where is my order, parcel status, shipping update, tracking number, delivery status',
      intents: ['package_tracking', 'shipment_status'],
      params: ['trackingNumber'],
      fallback: 'web_search'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true, source: '1password', item: '17TRACK API', field: 'credential' }
    ]
  },

  amadeus: {
    id: 'amadeus',
    name: 'Amadeus',
    category: 'travel',
    labels: ['travel', 'flight', 'hotel', 'booking'],
    icon: '✈️',
    auth: 'oauth2',
    description: 'Flight and hotel search (production)',
    skill: {
      useWhen: 'flight tickets, hotel availability, book travel, flights to X, find flights, airfare, round trip, one way, hotel prices, book hotel, find hotels, check fares',
      intents: ['flight_search', 'airfare_lookup', 'lodging_search', 'travel_booking', 'price_check'],
      params: ['origin + destination (flights) or cityCode (hotels)', 'departureDate or checkIn (YYYY-MM-DD)', 'checkOut (YYYY-MM-DD)', 'adults'],
      fallback: 'web_search'
    },
    dataPolicy: {
      allowedInputs: ['dates', 'location', 'public_info'],
      blockedInputs: ['passport_data', 'credentials'],
      requiresConfirmation: false,
      auditLevel: 'standard'
    },
    sandbox: {
      fieldKey: 'environment',
      testValue: 'test',
      warning: 'Sandbox mode — returns simulated data, not live inventory'
    },
    fields: [
      { key: 'clientId', label: 'Client ID', type: 'text', required: true, source: '1password', item: 'Amadeus API', field: 'credential' },
      { key: 'clientSecret', label: 'Client Secret', type: 'password', required: true, sensitive: true, source: '1password', item: 'Amadeus API', field: 'Private API key' },
      { key: 'environment', label: 'Environment', type: 'select', required: true, options: ['production', 'test'], default: 'production' }
    ]
  },

  telegram: {
    id: 'telegram',
    name: 'Telegram Bot',
    category: 'messaging',
    labels: ['messaging', 'chat', 'bot', 'notifications'],
    icon: '💬',
    description: 'Bot integration',
    fields: [
      { key: 'botToken', label: 'Bot Token', type: 'password', required: true, sensitive: true, help: 'From @BotFather' },
      { key: 'chatId', label: 'Chat ID', type: 'text', required: false, placeholder: '58748195' }
    ]
  },

  weather: {
    id: 'weather',
    name: 'Weather',
    category: 'lifestyle',
    labels: ['weather', 'lifestyle'],
    icon: '🌤️',
    description: 'Weather data (Open-Meteo, no key needed)',
    skill: {
      useWhen: 'weather, temperature, forecast, will it rain, wind, humidity, conditions today, weather this week',
      intents: ['weather_current', 'weather_forecast'],
      params: ['location (city or coords)'],
      fallback: 'web_search',
      note: 'No API key needed. Does NOT provide severe weather alerts — use official apps for that.'
    },
    fields: [
      { key: 'provider', label: 'Provider', type: 'select', required: true, options: ['open-meteo', 'openweathermap'], default: 'open-meteo' },
      { key: 'apiKey', label: 'API Key (if OWM)', type: 'password', required: false, sensitive: true, help: 'Only needed for OpenWeatherMap' }
    ]
  },

  elevenlabs: {
    id: 'elevenlabs',
    name: 'ElevenLabs',
    category: 'voice',
    labels: ['voice', 'tts', 'audio', 'speech'],
    icon: '🗣️',
    description: 'Text-to-speech',
    skill: {
      useWhen: 'say this out loud, read this aloud, text to speech, voice message, speak this, audio version',
      intents: ['text_to_speech', 'voice_output'],
      params: ['text', 'voiceId (optional)'],
      fallback: 'none'
    },
    dataPolicy: {
      allowedInputs: ['queries', 'public_info'],
      blockedInputs: ['client_pii', 'passport_data', 'credentials'],
      requiresConfirmation: false,
      auditLevel: 'none'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true, source: 'openclaw-skill', skill: 'sag' },
      { key: 'defaultVoiceId', label: 'Default Voice ID', type: 'text', required: false, placeholder: 'cgSgspJ2msm6clMCkdW9' }
    ]
  },

  duffel: {
    id: 'duffel',
    name: 'Duffel',
    category: 'travel',
    labels: ['travel', 'flight', 'booking', 'airfare'],
    icon: '🎫',
    description: 'Flight search and booking (primary). Use Python client, not raw curl. Hotels: use Amadeus.',
    skill: {
      useWhen: 'flight search, find flights, book flight, rates for route, find me flights, look me the rates, search flights, airfare',
      intents: ['flight_price_lookup'],
      params: ['origin (IATA)', 'destination (IATA)', 'departureDate (YYYY-MM-DD)', 'cabinClass', 'adults', 'returnDate (optional)'],
      fallback: 'amadeus',
      note: 'AGENT: Mandatory first step — read ~/.openclaw/workspace/duffel/HANDBOOK.md before answering any Duffel, flight search, fare display, booking, or offer-detail request. Then use duffel_client_v2.py — cd ~/.openclaw/workspace/duffel && python3 duffel_client_v2.py search <ORIGIN> <DEST> <DATE> [--cabin business]. Follow the canonical search → list → show/expand → book workflow from the handbook. Direct flights first, but never direct-only. Apply 3% markup for client quotes. Fallback to Amadeus if no offers or EK/LX route. Do not improvise alternate flight presentation formats when the handbook exists.'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  aviationstack: {
    id: 'aviationstack',
    name: 'Aviationstack',
    category: 'travel',
    labels: ['travel', 'flight-status', 'aviation', 'operations'],
    icon: '🛫',
    description: 'Flight status API',
    skill: {
      useWhen: 'flight status, is my flight on time, flight delay, flight tracker, flight number status, departure arrival status',
      intents: ['flight_status', 'flight_tracking'],
      params: ['flightNumber or iataCode', 'date (optional)'],
      fallback: 'web_search'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  goplaces: {
    id: 'goplaces',
    name: 'Google Places',
    category: 'location',
    labels: ['location', 'search', 'travel', 'maps'],
    icon: '📍',
    description: 'Places API (New)',
    skill: {
      useWhen: 'find restaurant, nearby places, best X in city, place details, opening hours, address, location info, hotels near me',
      intents: ['place_search', 'location_lookup', 'nearby_search', 'lodging_search'],
      params: ['query or placeName', 'location (city/coords)', 'type (restaurant/hotel/etc)'],
      fallback: 'web_search'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  newsapi: {
    id: 'newsapi',
    name: 'NewsAPI',
    category: 'news',
    labels: ['news', 'search', 'fresh-data'],
    icon: '📰',
    description: 'News headlines',
    skill: {
      useWhen: 'latest news, news about X, headlines, what happened with, recent events, news search',
      intents: ['news_search', 'headlines'],
      params: ['query or topic', 'language (optional)', 'from/to date (optional)'],
      fallback: 'brave_search'
    },
    dataPolicy: {
      allowedInputs: ['queries', 'dates', 'public_info'],
      blockedInputs: ['client_pii', 'credentials'],
      requiresConfirmation: false,
      auditLevel: 'none'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  openexchangerates: {
    id: 'openexchangerates',
    name: 'Open Exchange Rates',
    category: 'finance',
    labels: ['finance', 'currency', 'fx', 'rates'],
    icon: '💱',
    description: 'Currency conversion',
    skill: {
      useWhen: 'currency conversion, exchange rate, convert EUR to USD, how much is X in Y, forex rate',
      intents: ['currency_conversion', 'exchange_rate'],
      params: ['fromCurrency', 'toCurrency', 'amount (optional)'],
      fallback: 'web_search'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  whisper: {
    id: 'whisper',
    name: 'OpenAI Whisper',
    category: 'audio',
    labels: ['audio', 'transcription', 'speech-to-text', 'voice'],
    icon: '🎙️',
    description: 'Speech-to-text',
    skill: {
      useWhen: 'transcribe audio, transcribe this file, speech to text, what does this audio say, convert audio to text',
      intents: ['audio_transcription', 'speech_to_text'],
      params: ['audioFilePath or URL'],
      fallback: 'none'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  mem0: {
    id: 'mem0',
    name: 'Mem0',
    category: 'memory',
    labels: ['long-term-memory'],
    icon: '🧠',
    description: 'Long-term memory layer for AI assistants',
    skill: {
      useWhen: 'long-term memory, persistent memory, memory plugin, user profile memory, cross-session context',
      intents: ['memory_management', 'memory_search', 'memory_store'],
      params: ['apiKey', 'userId (optional)', 'orgId (optional)', 'projectId (optional)'],
      fallback: 'none'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true, help: 'From app.mem0.ai' },
      { key: 'userId', label: 'Default User ID', type: 'text', required: false, placeholder: 'alex' },
      { key: 'orgId', label: 'Org ID', type: 'text', required: false },
      { key: 'projectId', label: 'Project ID', type: 'text', required: false },
      { key: 'mode', label: 'Mode', type: 'select', required: false, options: ['platform', 'open-source'], default: 'platform' }
    ]
  },

  vapi: {
    id: 'vapi',
    name: 'VAPI',
    category: 'voice',
    labels: ['voice', 'telephony', 'agent', 'automation'],
    icon: '📞',
    description: 'Voice AI platform',
    skill: {
      useWhen: 'make a phone call, call this number, outbound call, voice agent, phone assistant',
      intents: ['phone_call', 'voice_agent'],
      params: ['phoneNumber', 'assistantId (optional)', 'message or context'],
      fallback: 'none'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true },
      { key: 'assistantId', label: 'Assistant ID', type: 'text', required: false },
      { key: 'phoneNumberId', label: 'Phone Number ID', type: 'text', required: false }
    ]
  },

  brave: {
    id: 'brave',
    name: 'Brave Search',
    category: 'search',
    labels: ['search', 'news', 'research', 'fresh-data'],
    icon: '🦁',
    description: 'Web search API',
    skill: {
      useWhen: 'search the web, find information, look up X, research topic, web search, browse for',
      intents: ['web_search', 'research', 'information_lookup'],
      params: ['query'],
      fallback: 'perplexity',
      note: 'Used automatically by the web_search tool. Call directly only for raw search API access.'
    },
    dataPolicy: {
      allowedInputs: ['queries', 'dates', 'public_info', 'location'],
      blockedInputs: ['client_pii', 'passport_data', 'financial_records', 'credentials'],
      requiresConfirmation: false,
      auditLevel: 'standard'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  perplexity: {
    id: 'perplexity',
    name: 'Perplexity',
    category: 'ai',
    labels: ['ai', 'search', 'news', 'research', 'fresh-data'],
    icon: '🔮',
    description: 'AI search',
    skill: {
      useWhen: 'research with AI, deep dive into topic, explain and search, AI-powered research, summarize current events',
      intents: ['ai_research', 'deep_search', 'news_analysis'],
      params: ['query'],
      fallback: 'brave'
    },
    dataPolicy: {
      allowedInputs: ['queries', 'dates', 'public_info'],
      blockedInputs: ['client_pii', 'passport_data', 'credentials'],
      requiresConfirmation: false,
      auditLevel: 'standard'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  'google-workspace': {
    id: 'google-workspace',
    name: 'Google Workspace',
    category: 'productivity',
    labels: ['gmail', 'drive', 'calendar', 'sheets'],
    icon: '🔷',
    description: 'Gmail, Calendar, Drive',
    skill: {
      useWhen: 'check email, send email, calendar events, upcoming meetings, schedule, google drive, create document',
      intents: ['email_read', 'email_send', 'calendar_check', 'calendar_create', 'drive_access'],
      params: ['query or event details', 'date/time (for calendar)', 'recipient (for email)'],
      fallback: 'none'
    },
    dataPolicy: {
      allowedInputs: ['client_pii', 'business_internal', 'dates', 'queries', 'location'],
      blockedInputs: ['credentials'],
      requiresConfirmation: true,
      auditLevel: 'full'
    },
    fields: [
      { key: 'account', label: 'Account Email', type: 'text', required: true, sensitive: false, placeholder: 'user@domain.com' },
      { key: 'oauthClientJson', label: 'OAuth Client JSON Path', type: 'text', required: true, placeholder: '~/.config/gog/client_secret_...json' },
      { key: 'gogClient', label: 'gog Client Name', type: 'text', required: false, sensitive: false, placeholder: 'default' },
      { key: 'gwsConfigDir', label: 'gws Config Dir', type: 'text', required: false, sensitive: false, placeholder: '~/.config/gws' },
      { key: 'keyringPassword', label: 'Keyring Password', type: 'password', required: true, sensitive: true },
      { key: 'keyringPasswordSource', label: 'Keyring Password Source', type: 'select', required: false, options: ['1password', 'file', 'env'], default: 'file' }
    ],
    multiAccount: {
      supported: true,
      labelRequired: true,
      docRef: 'tools-server/GOOGLE-WORKSPACE.md'
    }
  },

  n8n: {
    id: 'n8n',
    name: 'n8n',
    category: 'automation',
    labels: ['automation', 'workflow', 'integration', 'orchestration'],
    icon: '⚙️',
    description: 'Workflow automation',
    skill: {
      useWhen: 'trigger workflow, run automation, execute n8n flow, webhook trigger, automate task',
      intents: ['workflow_trigger', 'automation_run'],
      params: ['workflowId or webhookPath', 'payload (optional)'],
      fallback: 'none'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true, source: '1password', item: 'n8n API', field: 'credential' },
      { key: 'hostUrl', label: 'Host URL', type: 'url', required: true, placeholder: 'https://n8n.example.com', source: '1password', item: 'n8n API', field: 'hostname' },
      { key: 'webhook17track', label: '17TRACK Webhook', type: 'url', required: false, placeholder: 'https://n8n.../webhook/17track-to-mel' }
    ]
  },

  nanoBanana: {
    id: 'nanoBanana',
    name: 'Nano Banana Pro',
    category: 'image',
    labels: ['image', 'generation', 'creative', 'design'],
    icon: '🖼️',
    description: 'Image generation',
    skill: {
      useWhen: 'generate image, create image, draw, make a picture, illustrate, design visual, edit image',
      intents: ['image_generation', 'image_edit'],
      params: ['prompt', 'resolution (optional: 1K/2K/4K)', 'inputImage (optional for edits)'],
      fallback: 'none',
      note: 'Use the nano-banana-pro skill.'
    },
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  // ── Infrastructure services (managed by OpenClaw runtime) ──────────────────
  // These are not called directly by the agent. Listed for completeness only.

  '1password': {
    id: '1password',
    name: '1Password',
    category: 'security',
    labels: ['security', 'secrets', 'credentials', 'vault'],
    icon: '🔐',
    description: 'Secret retrieval via op CLI',
    skill: {
      useWhen: 'retrieve secret, get API key from vault, op read, fetch credential, read password, 1password lookup',
      intents: ['secret_retrieval', 'credential_lookup'],
      params: ['vault path (op://vault/item/field)'],
      fallback: 'tools_server',
      note: 'Use `op read "op://vault/item/field"`. Prefer tools server /api/credentials for known services.'
    },
    fields: [
      { key: 'serviceAccountToken', label: 'Service Account Token', type: 'password', required: true, sensitive: true, placeholder: 'ops_...' },
      { key: 'account', label: 'Account Name', type: 'text', required: false, placeholder: 'prudkov' },
      { key: 'vault', label: 'Default Vault', type: 'text', required: false, placeholder: 'Alex-Mel' }
    ]
  },

  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    category: 'ai',
    labels: ['ai', 'llm', 'reasoning', 'analysis'],
    icon: '🧠',
    description: 'Claude models — managed by OpenClaw runtime',
    infrastructure: true,
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  openai: {
    id: 'openai',
    name: 'OpenAI',
    category: 'ai',
    labels: ['ai', 'llm', 'generation', 'reasoning'],
    icon: '🤖',
    description: 'GPT models — managed by OpenClaw runtime',
    infrastructure: true,
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true },
      { key: 'orgId', label: 'Organization ID', type: 'text', required: false }
    ]
  },

  moonshot: {
    id: 'moonshot',
    name: 'Moonshot',
    category: 'ai',
    labels: ['ai', 'llm', 'reasoning', 'chat'],
    icon: '🌙',
    description: 'Kimi models — managed by OpenClaw runtime',
    infrastructure: true,
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  google: {
    id: 'google',
    name: 'Google (Gemini API)',
    category: 'ai',
    labels: ['ai', 'llm', 'gemini', 'reasoning'],
    icon: '🟦',
    description: 'Gemini models — managed by OpenClaw runtime',
    infrastructure: true,
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true }
    ]
  },

  pinecone: {
    id: 'pinecone',
    name: 'Pinecone',
    category: 'vector-db',
    labels: ['vector-db', 'search', 'rag', 'embeddings', 'knowledge'],
    icon: '🌲',
    description: 'Vector database — used by memory_search + Via Travel SOPs',
    infrastructure: true,
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, sensitive: true },
      { key: 'indexHost', label: 'Index Host', type: 'text', required: true,
        placeholder: 'https://your-index-abc123.svc.aped-xxxx.pinecone.io',
        help: 'Paste the full URL from Pinecone dashboard — https:// is stripped automatically' },
      { key: 'indexName', label: 'Index Name', type: 'text', required: false, placeholder: 'sop-docs' },
      { key: 'environment', label: 'Environment', type: 'text', required: false, placeholder: 'us-east-1' }
    ]
  },

  telegram: {
    id: 'telegram',
    name: 'Telegram Bot',
    category: 'messaging',
    labels: ['messaging', 'chat', 'bot', 'notifications'],
    icon: '💬',
    description: 'Bot integration — managed by OpenClaw runtime',
    infrastructure: true,
    fields: [
      { key: 'botToken', label: 'Bot Token', type: 'password', required: true, sensitive: true, help: 'From @BotFather' },
      { key: 'chatId', label: 'Chat ID', type: 'text', required: false, placeholder: '58748195' }
    ]
  },

  hubspot: {
    id: 'hubspot',
    name: 'HubSpot',
    category: 'crm',
    labels: ['crm', 'sales', 'marketing', 'contacts'],
    icon: '🟠',
    description: 'CRM integration',
    infrastructure: true,
    fields: [
      { key: 'accessToken', label: 'Private Access Token', type: 'password', required: true, sensitive: true }
    ]
  },

  groove: {
    id: 'groove',
    name: 'Groove',
    category: 'support',
    labels: ['support', 'tickets', 'customer-service', 'helpdesk'],
    icon: '🎧',
    description: 'Customer support and ticketing platform',
    skill: {
      useWhen: 'check support tickets, list tickets, create ticket, reply to customer, Groove ticket, helpdesk, customer support',
      intents: ['ticket_list', 'ticket_create', 'ticket_reply', 'support_monitor'],
      params: ['ticketId (optional)', 'customerEmail (optional)', 'status (optional)'],
      fallback: 'none'
    },
    dataPolicy: {
      allowedInputs: ['client_pii', 'business_internal', 'dates', 'queries'],
      blockedInputs: ['credentials'],
      requiresConfirmation: false,
      auditLevel: 'standard'
    },
    fields: [
      { key: 'apiToken', label: 'API Token', type: 'password', required: true, sensitive: true, help: 'From Groove account settings → API section (admin access required)' },
      { key: 'baseUrl', label: 'Base URL', type: 'url', required: true, placeholder: 'https://api.groovehq.com/v1/', default: 'https://api.groovehq.com/v1/' }
    ]
  }
};

module.exports = { SERVICE_SCHEMAS, AGENT_SCHEMA };