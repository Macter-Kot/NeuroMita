API_PRESETS_DATA = [
    {
        "id": 1,
        "name": "Gpt4Free",
        "pricing": "free",
        "default_model": "deepseek-v3",
        "known_models": ["deepseek-v3", "gpt-4o-mini", "claude-3.5-sonnet"],
        "is_g4f": True,
        "use_request": False,
        "documentation_url": "https://github.com/xtekky/gpt4free"
    },
    {
        "id": 2,
        "name": "OpenRouter",
        "pricing": "mixed",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "google/gemini-2.0-flash-exp:free",
        "known_models": [
            "google/gemini-2.0-flash-exp:free",
            "google/gemini-2.0-flash-thinking-exp:free",
            "meta-llama/llama-3.2-3b-instruct:free"
        ],
        "gemini_case": None,
        "use_request": False,
        "add_key": False,
        "documentation_url": "https://openrouter.ai/keys"
    },
    {
        "id": 3,
        "name": "Ai.iO",
        "pricing": "mixed",
        "url": "https://api.intelligence.io.solutions/api/v1/",
        "default_model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "known_models": [],
        "use_request": False,
        "add_key": False,
        "documentation_url": "https://intelligence.io.solutions"
    },
    {
        "id": 4,
        "name": "Google AI Studio",
        "pricing": "mixed",
        "url_tpl": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "default_model": "gemini-2.0-flash-exp",
        "known_models": [
            "gemini-2.0-flash-exp",
            "gemini-2.0-flash-thinking-exp-1219",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-1.5-pro"
        ],
        "gemini_case": True,
        "use_request": True,
        "add_key": True,
        "test_url": "https://generativelanguage.googleapis.com/v1beta/models?key={key}",
        "filter_fn": "filter_generate_content",
        'documentation_url': 'https://ai.google.dev/gemini-api/docs',
        'models_url': 'https://ai.google.dev/gemini-api/docs/models/gemini',
        'key_url': 'https://aistudio.google.com/apikey'
    },
    {
        "id": 5,
        "name": "ProxiApi (google)",
        "pricing": "paid",
        "url_tpl": "https://api.proxyapi.ru/google/v1/models/{model}:generateContent",
        "default_model": "gemini-2.0-flash-lite",
        "known_models": ["gemini-2.0-flash-lite", "gemini-1.5-flash"],
        "gemini_case": True,
        "use_request": True,
        "add_key": False,
        "documentation_url": "https://proxyapi.ru"
    },
    {
        "id": 6,
        "name": "ProxiApi (deepseek)",
        "pricing": "paid",
        "url": "https://api.proxyapi.ru/deepseek",
        "default_model": "deepseek-chat",
        "known_models": ["deepseek-chat", "deepseek-reasoner"],
        "use_request": False,
        "add_key": False,
        "documentation_url": "https://proxyapi.ru"
    },
    {
        "id": 7,
        "name": "OpenAI",
        "pricing": "paid",
        "url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
        "known_models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "o1-mini", "o1-preview"],
        "use_request": False,
        "add_key": False,
        "documentation_url": "https://platform.openai.com/api-keys"
    },
    {
        "id": 8,
        "name": "Anthropic",
        "pricing": "paid",
        "url": "https://api.anthropic.com/v1/messages",
        "default_model": "claude-3-5-sonnet-20241022",
        "known_models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "use_request": False,
        "add_key": False,
        "documentation_url": "https://console.anthropic.com/settings/keys"
    },
    {
        "id": 9,
        "name": "DeepSeek",
        "pricing": "paid",
        "url": "https://api.deepseek.com/chat/completions",
        "default_model": "deepseek-chat",
        "known_models": ["deepseek-chat", "deepseek-reasoner"],
        "use_request": False,
        "add_key": False,
        "documentation_url": "https://platform.deepseek.com/api_keys"
    },
    {
        "id": 10,
        "name": "Chutes.ai",
        "pricing": "paid",
        "url": "https://llm.chutes.ai/v1/chat/completions",
        "default_model": "deepseek-ai/DeepSeek-V3-0324",
        "known_models": ["deepseek-ai/DeepSeek-V3-0324"],
        "use_request": True,
        "add_key": False,
        "documentation_url": "https://chutes.ai"
    }
]