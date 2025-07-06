# tools/web_search.py
import os, json, re, requests, bs4
from urllib.parse import quote_plus
from .base import Tool

# ────────────────────────────────────────────────────────────────────
#  CONFIG / API KEYS (можно также держать в settings.json)
# ────────────────────────────────────────────────────────────────────
RAPIDAPI_KEY   = os.getenv("RAPIDAPI_KEY", "")         # для Bing / ContextualWeb
DEFAULT_PROV   = os.getenv("TOOL_WEB_SEARCH_PROVIDER", "duckduckgo")

DDG_HTML_URL   = "https://duckduckgo.com/html/?q={query}"
BING_API_URL   = "https://bing-web-search1.p.rapidapi.com/search"
GOOG_API_URL   = "https://contextualwebsearch-websearch-v1.p.rapidapi.com/api/Search/WebSearchAPI"

# ────────────────────────────────────────────────────────────────────
class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Делает интернет-поиск и возвращает JSON-массив результатов "
        "(title, url, snippet). Поддерживаемые провайдеры: "
        "duckduckgo (по умолчанию), bing, google."
    )

    parameters = {
        "type": "object",
        "properties": {
            "query":      {"type": "string",  "description": "Поисковый запрос"},
            "provider":   {"type": "string",  "description": "bing | duckduckgo | google"},
            "top_k":      {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            "lang":       {"type": "string",  "description": "Код языка, напр. 'ru', 'en'"},
            "region":     {"type": "string",  "description": "Страна, напр. 'ru', 'us'"},
            "site":       {"type": "string",  "description": "Ограничить поиск доменом, напр. 'bbc.com'"},
            "news_only": {
                "type": "boolean",
                "description": "Искать только новости (Google News / Bing News)",
                "default": False
            },
        },
        "required": ["query"],

    }

    # ────────────────────────────────────────────────────────────────
    def run(self, query: str,
                  provider: str | None = None,
                  top_k: int = 3,
                  lang: str | None = None,
                  region: str | None = None,
                  site: str | None = None,
                  **_) -> str:

        provider = (provider or DEFAULT_PROV).lower()
        if site:
            query = f"site:{site} {query}"
        if lang:
            query += f" language:{lang}"

        try:
            if provider == "bing":
                results = self._search_bing(query, top_k, lang, region)
            elif provider == "google":
                results = self._search_google(query, top_k, lang, region)
            else:                                    # duckduckgo
                results = self._search_ddg(query, top_k)
        except Exception as e:
            return f"[web_search] Ошибка: {e}"

        if not results:
            return "[web_search] Ничего не найдено"

        return json.dumps(results, ensure_ascii=False, indent=2)

    # ───── DuckDuckGo (HTML-scrape) ─────────────────────────────────
    def _search_ddg(self, query: str, top_k: int):
        url = DDG_HTML_URL.format(query=quote_plus(query))
        html = requests.get(url, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"}).text
        soup = bs4.BeautifulSoup(html, "html.parser")
        out = []
        for res in soup.select(".result")[:top_k]:
            a = res.select_one(".result__a")
            snippet = res.select_one(".result__snippet")
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            link  = a["href"]
            desc  = snippet.get_text(" ", strip=True) if snippet else ""
            desc  = re.sub(r"\s{2,}", " ", desc)
            out.append({"title": title, "url": link, "snippet": desc})
        return out

    # ───── Bing Web Search API (RapidAPI) ───────────────────────────
    def _search_bing(self, query: str, top_k: int, lang: str | None, region: str | None):
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "bing-web-search1.p.rapidapi.com"
        }
        params = {"q": query, "mkt": f"{lang}-{region}" if lang and region else "en-US", "count": top_k}
        data = requests.get(BING_API_URL, headers=headers, params=params, timeout=10).json()
        out = []
        for item in data.get("webPages", {}).get("value", [])[:top_k]:
            out.append({
                "title":   item.get("name"),
                "url":     item.get("url"),
                "snippet": item.get("snippet")
            })
        return out

    # ───── ContextualWeb (Google-like) ─────────────────────────────
    def _search_google(self, query: str, top_k: int, lang: str | None, region: str | None):
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "contextualwebsearch-websearch-v1.p.rapidapi.com"
        }
        params = {
            "q": query,
            "pageNumber": 1,
            "pageSize": top_k,
            "autoCorrect": "true",
            "safeSearch": "true",
        }
        if lang:
            params["language"] = lang
        data = requests.get(GOOG_API_URL, headers=headers, params=params, timeout=10).json()
        out = []
        for item in data.get("value", [])[:top_k]:
            out.append({
                "title":   item.get("title"),
                "url":     item.get("url"),
                "snippet": item.get("description")
            })
        return out