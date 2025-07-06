# presets/api_presets.py
API_PRESETS = {

    # бесплатные / условно-бесплатные сервисы
    "🕊️/💲 OpenRouter":  {"url": "https://openrouter.ai/api/v1/chat/completions", "model": "google/gemini-2.0-pro-exp-02-05:free"},
    "🕊️/💲 Ai.iO":       {"url": "https://api.intelligence.io.solutions/api/v1/", "model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"},
    "🕊️/💲 Chutes.ai":   {"url": "https://llm.chutes.ai/v1/chat/completions",  "model": "deepseek-ai/DeepSeek-V3-0324"},


    # Google
    "️🕊️/💲Google AI Studio": {"url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent", "model": "gemini-2.5-flash",
                         "nm_api_req": True,
                         "gemini_case": True},
    # классические
    "💲 OpenAI": {"url": "https://api.openai.com/v1/chat/completions", "model": "gpt-4o-mini"},
    "💲 Anthropic": {"url": "https://api.anthropic.com/v1/messages", "model": "claude-3-opus-20240229"},
    "💲 DeepSeek": {"url": "https://api.deepseek.com/chat/completions", "model": "deepseek-chat"},

    # ProxiApi
    "💲 ProxiApi (for google)": {"url": "https://api.proxyapi.ru/google/v1/models/gemini-2.0-flash-lite:generateContent", "model": "gemini-2.0-flash-lite",
                         "nm_api_req": True,
                         "gemini_case": True},
    "💲 ProxiApi (for deepseek)": {"url": "https://api.proxyapi.ru/deepseek",
                              "model": "deepseek-chat",
                              "nm_api_req": False,
                              "gemini_case": False},

}