PRICING_SYMBOLS = {
    'free':  '🕊️',
    'paid':  '💲',
    'mixed': '🕊️/💲',
}

API_PRESETS: dict = {

    # Условно-бесплатные / бесплатные
    "openrouter": {
        "name": "OpenRouter",
        "pricing": "mixed",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "add_key": False,
        "model": "google/gemini-2.0-pro-exp-02-05:free",
        "nm_api_req": False,
        "gemini_case": False,
    },
    "aiio": {
        "name": "Ai.iO",
        "pricing": "mixed",
        "url": "https://api.intelligence.io.solutions/api/v1/",
        "add_key": False,
        "model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "nm_api_req": False,
        "gemini_case": False,
    },
    "chutes": {
        "name": "Chutes.ai",
        "pricing": "mixed",
        "url": "https://llm.chutes.ai/v1/chat/completions",
        "add_key": False,
        "model": "deepseek-ai/DeepSeek-V3-0324",
        "nm_api_req": True,
        "gemini_case": False,
    },

    # Google
    "google_ai_studio": {
        "name": "Google AI Studio",
        "pricing": "mixed",
        "url_tpl": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "add_key": True,
        "model": "gemini-2.5-flash",
        "nm_api_req": True,
        "gemini_case": True,
    },

    # ProxiApi
    "proxiapi_google": {
        "name": "ProxiApi (google)",
        "pricing": "paid",
        "url_tpl": "https://api.proxyapi.ru/google/v1/models/{model}:generateContent",
        "add_key": False,
        "model": "gemini-2.0-flash-lite",
        "nm_api_req": True,
        "gemini_case": True,
    },
    "proxiapi_deepseek": {
        "name": "ProxiApi (deepseek)",
        "pricing": "paid",
        "url_tpl": "https://api.proxyapi.ru/deepseek",
        "add_key": False,
        "model": "deepseek-chat",
        "nm_api_req": False,
        "gemini_case": False,
    },

    # Классические коммерческие
    "openai": {
        "name": "OpenAI",
        "pricing": "paid",
        "url": "https://api.openai.com/v1/chat/completions",
        "add_key": False,
        "model": "gpt-4o-mini",
        "gemini_case": False,
    },
    "anthropic": {
        "name": "Anthropic",
        "pricing": "paid",
        "url": "https://api.anthropic.com/v1/messages",
        "add_key": False,
        "model": "claude-3-opus-20240229",
        "nm_api_req": False,
        "gemini_case": False,
    },
    "deepseek": {
        "name": "DeepSeek",
        "pricing": "paid",
        "url": "https://api.deepseek.com/chat/completions",
        "add_key": False,
        "model": "deepseek-chat",
        "nm_api_req": False,
        "gemini_case": False,
    },


}