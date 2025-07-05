import requests
import base64

"Позволит в итоге анализировать картинки"


# Ваш API-ключ OpenRouter
API_KEY = "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" # халявный, я его вырублю)

# Путь к изображению
image_path = "C:\\Users\\Dmitry\\Downloads\\NeuroMita2.png"

# Чтение и кодирование изображения в base64
with open(image_path, "rb") as image_file:
    encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

# Заголовки запроса
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Тело запроса
data = {
    "model": "google/gemini-2.0-flash-lite-preview-02-05:free",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Что изображено на этой картинке?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_image}"}}
            ]
        }
    ],
    "top_p": 1,
    "temperature": 0.7,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "repetition_penalty": 1,
    "top_k": 0
}

# Отправка запроса
response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers=headers,
    json=data
)

# Вывод результата
if response.status_code == 200:
    logger.info("Ответ от API:")
    logger.info(response.json())
else:
    logger.info("Ошибка при выполнении запроса:")
    logger.info(f"Код статуса: {response.status_code}")
    logger.info(f"Ответ: {response.text}")