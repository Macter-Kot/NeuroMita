from typing import List, Optional
from handlers.llm_providers.base import BaseProvider, LLMRequest
from handlers.llm_providers.openai_provider import OpenAIProvider
from handlers.llm_providers.gemini_provider import GeminiProvider
from handlers.llm_providers.common_provider import CommonProvider
from handlers.llm_providers.g4f_provider import G4FProvider
from main_logger import logger

class ProviderManager:
    def __init__(self):
        self._providers: List[BaseProvider] = []
        self._register_providers()

    def _register_providers(self):
        self._providers = [
            OpenAIProvider(),
            GeminiProvider(),
            CommonProvider(),
            G4FProvider()
        ]
        self._providers.sort(key=lambda p: p.priority)
        logger.info(f"Registered {len(self._providers)} providers")

    def generate(self, req: LLMRequest) -> Optional[str]:
        for provider in self._providers:
            if provider.is_applicable(req):
                logger.info(f"Using provider: {provider.name}")
                return provider.generate(req)
        logger.error("No provider can handle this request")
        raise RuntimeError("No provider can handle this request")