# tools/web_reader.py
import re, requests, bs4
from .base import Tool

_CLEAN_TAGS = ["script", "style", "noscript", "iframe", "header",
               "footer", "nav", "aside", "form"]

class WebPageReaderTool(Tool):
    name = "web_reader"
    description = "Скачивает веб-страницу и возвращает очищенный текст."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Полный URL страницы (http/https)"
            },
            "max_chars": {
                "type": "integer",
                "description": "Максимальное число символов (по умолчанию 1500)",
                "default": 1500,
                "minimum": 100,
                "maximum": 8000
            }
        },
        "required": ["url"]
    }

    # --- основной метод -------------------------------------------------
    def run(self, url: str, max_chars: int = 1500, **_):
        try:
            resp = requests.get(url, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception as e:
            return f"[web_reader] Ошибка при загрузке: {e}"

        soup = bs4.BeautifulSoup(resp.text, "html.parser")

        # 1) удаляем мусорные теги
        for tg in _CLEAN_TAGS:
            for tag in soup.find_all(tg):
                tag.decompose()

        # 2) получаем чистый текст
        text = soup.get_text(" ", strip=True)
        # убираем множественные пробелы/переводы строк
        text = re.sub(r"\s{2,}", " ", text)

        if not text:
            return "[web_reader] Ничего не удалось извлечь."

        # 3) обрезаем
        if len(text) > max_chars:
            text = text[:max_chars] + " …"

        return text