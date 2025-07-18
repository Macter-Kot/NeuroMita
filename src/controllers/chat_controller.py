import asyncio
import time
from main_logger import logger
from core.events import get_event_bus, Events, Event

# Контроллер для работы с отправкой сообщений.
class ChatController:
    def __init__(self, settings):
        self.settings = settings
        self.event_bus = get_event_bus()
        self.llm_processing = False
        
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.SEND_MESSAGE, self._on_send_message, weak=False)
        self.event_bus.subscribe(Events.GET_LLM_PROCESSING_STATUS, self._on_get_llm_processing_status, weak=False)
        self.event_bus.subscribe("send_periodic_image_request", self._on_send_periodic_image_request, weak=False)
        
    async def async_send_message(
        self,
        user_input: str,
        system_input: str = "",
        image_data: list[bytes] | None = None
    ):
        try:
            print("[DEBUG] Начинаем async_send_message, показываем статус")
            self.llm_processing = True
            
            is_streaming = bool(self.settings.get("ENABLE_STREAMING", False))

            def stream_callback_handler(chunk: str):
                self.event_bus.emit(Events.APPEND_STREAM_CHUNK_UI, {'chunk': chunk})

            if is_streaming:
                self.event_bus.emit(Events.PREPARE_STREAM_UI)

            
            message_id = getattr(self, 'current_message_id', None)

            response_result = self.event_bus.emit_and_wait(Events.GENERATE_RESPONSE, {
                'user_input': user_input,
                'system_input': system_input,
                'image_data': image_data,
                'stream_callback': stream_callback_handler if is_streaming else None,
                'message_id': message_id  # Добавить это поле
            }, timeout=600.0)
            
            response = response_result[0] if response_result else None

            if is_streaming:
                self.event_bus.emit(Events.FINISH_STREAM_UI)
            else:
                self.event_bus.emit(Events.UPDATE_CHAT_UI, {
                    'role': 'assistant',
                    'response': response if response is not None else "...",
                    'is_initial': False,
                    'emotion': ''
                })

            self.event_bus.emit(Events.UPDATE_STATUS)
            self.event_bus.emit(Events.UPDATE_DEBUG_INFO)
            self.event_bus.emit(Events.UPDATE_TOKEN_COUNT)

            # Получаем сервер через событие
            server_result = self.event_bus.emit_and_wait(Events.GET_CHAT_SERVER, timeout=1.0)
            server = server_result[0] if server_result else None
            
            if server and server.client_socket:
                final_response_text = response if response else "..."
                try:
                    server.send_message_to_server(final_response_text)
                    logger.info("Ответ отправлен в игру.")
                except Exception as e:
                    logger.error(f"Не удалось отправить ответ в игру: {e}")
            
            self.llm_processing = False
            return response
                    
        except asyncio.TimeoutError:
            logger.warning("Тайм-аут: генерация ответа заняла слишком много времени.")
            self.llm_processing = False
            self.event_bus.emit(Events.ON_FAILED_RESPONSE, {'error': "Превышено время ожидания ответа"})
            return "Произошла ошибка при обработке вашего сообщения."
        except Exception as e:
            logger.error(f"Ошибка в async_send_message: {e}", exc_info=True)
            self.llm_processing = False
            self.event_bus.emit(Events.ON_FAILED_RESPONSE, {'error': f"Ошибка: {str(e)[:50]}..."})
            return "Произошла ошибка при обработке вашего сообщения."
    
    def _on_send_message(self, event: Event):
        data = event.data
        user_input = data.get('user_input', '')
        system_input = data.get('system_input', '')
        image_data = data.get('image_data', [])
        
        if image_data:
            self.event_bus.emit(Events.UPDATE_LAST_IMAGE_REQUEST_TIME)
        
        coro = self.async_send_message(user_input, system_input, image_data)
        
        self.event_bus.emit(Events.RUN_IN_LOOP, {
            'coroutine': coro,
            'callback': None
        })
    
    def _on_get_llm_processing_status(self, event: Event):
        return self.llm_processing
    
    def _on_send_periodic_image_request(self, event: Event):
        data = event.data
        
        if data.get('image_data'):
            self.event_bus.emit(Events.UPDATE_LAST_IMAGE_REQUEST_TIME)
        
        coro = self.async_send_message(
            user_input=data.get('user_input', ''),
            system_input=data.get('system_input', ''), 
            image_data=data.get('image_data', [])
        )
        
        self.event_bus.emit(Events.RUN_IN_LOOP, {
            'coroutine': coro,
            'callback': None
        })