# presets/api_presets.py
API_PRESETS = {
    # классические
    "OpenAI":      {"url": "https://api.openai.com/v1/chat/completions", "model": "gpt-4o-mini"},
    "Anthropic":   {"url": "https://api.anthropic.com/v1/messages",      "model": "claude-3-opus-20240229"},
    "DeepSeek":    {"url": "https://api.deepseek.com/chat/completions",  "model": "deepseek-chat"},

    # бесплатные / условно-бесплатные сервисы
    "OpenRouter":  {"url": "https://openrouter.ai/api/v1/chat/completions", "model": "google/gemini-2.0-pro-exp-02-05:free"},
    "Ai.iO":       {"url": "https://api.intelligence.io.solutions/api/v1/", "model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"},
    "Chutes.ai":   {"url": "https://llm.chutes.ai/v1/chat/completions",  "model": "deepseek-ai/DeepSeek-V3-0324"},

    # Google
    "Google AI Studio": {"url": "", "model": "gemini-2.5-flash"},                   # url собираем динамически
}