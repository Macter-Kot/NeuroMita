import threading
from typing import Dict, List, Callable, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import weakref
from dataclasses import dataclass
from queue import Queue, Empty
import time
from main_logger import logger


@dataclass
class Event:
    """Базовый класс для всех событий"""
    name: str
    data: Any = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class EventBus:
    """
    Потокобезопасная система событий с поддержкой слабых ссылок
    для предотвращения утечек памяти
    """
    
    def __init__(self, max_workers: int = 5):
        self._subscribers: Dict[str, List[weakref.ref]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._event_queue = Queue()
        self._running = True
        self._processor_thread = threading.Thread(target=self._process_events, daemon=True)
        self._processor_thread.start()
    
    def subscribe(self, event_name: str, callback: Callable, weak: bool = True) -> None:
        """
        Подписаться на событие
        
        Args:
            event_name: Имя события
            callback: Функция обратного вызова
            weak: Использовать слабую ссылку (рекомендуется True)
        """
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            
            if weak:
                # Используем слабую ссылку для предотвращения циклических ссылок
                weak_ref = weakref.ref(callback, self._create_cleanup_callback(event_name))
                self._subscribers[event_name].append(weak_ref)
            else:
                # Для статических функций можно использовать сильные ссылки
                self._subscribers[event_name].append(callback)
            
            logger.debug(f"Подписка на событие '{event_name}' добавлена")
    
    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        """Отписаться от события"""
        with self._lock:
            if event_name not in self._subscribers:
                return
            
            # Удаляем callback из списка подписчиков
            self._subscribers[event_name] = [
                ref for ref in self._subscribers[event_name]
                if not self._is_same_callback(ref, callback)
            ]
            
            # Удаляем пустые списки
            if not self._subscribers[event_name]:
                del self._subscribers[event_name]
    
    def emit(self, event_name: str, data: Any = None, sync: bool = False) -> None:
        """
        Отправить событие
        
        Args:
            event_name: Имя события
            data: Данные события
            sync: Выполнить синхронно (блокирующий вызов)
        """
        event = Event(name=event_name, data=data)
        
        # Добавить отладку
        with self._lock:
            subscribers_count = len(self._get_active_subscribers(event_name))
            if subscribers_count > 0:
                logger.debug(f"Emitting event '{event_name}' to {subscribers_count} subscribers")
            else:
                logger.warning(f"No subscribers for event '{event_name}'")
        
        if sync:
            self._emit_sync(event)
        else:
            self._event_queue.put(event)
    
    def emit_and_wait(self, event_name: str, data: Any = None, timeout: float = 5.0) -> List[Any]:
        """
        Отправить событие и дождаться результатов от всех подписчиков
        
        Returns:
            Список результатов от подписчиков
        """
        results = []
        result_queue = Queue()
        
        # Создаем специальный wrapper для сбора результатов
        def result_wrapper(callback):
            def wrapper(*args, **kwargs):
                try:
                    result = callback(*args, **kwargs)
                    result_queue.put(result)
                except Exception as e:
                    logger.error(f"Ошибка в обработчике события: {e}")
                    result_queue.put(None)
            return wrapper
        
        with self._lock:
            subscribers = self._get_active_subscribers(event_name)
        
        if not subscribers:
            return results
        
        # Запускаем все обработчики
        for subscriber in subscribers:
            wrapped = result_wrapper(subscriber)
            self._executor.submit(wrapped, Event(name=event_name, data=data))
        
        # Собираем результаты с таймаутом
        start_time = time.time()
        collected = 0
        
        while collected < len(subscribers) and (time.time() - start_time) < timeout:
            try:
                result = result_queue.get(timeout=0.1)
                if result is not None:
                    results.append(result)
                collected += 1
            except Empty:
                continue
        
        return results
    
    def shutdown(self) -> None:
        """Остановить систему событий"""
        self._running = False
        self._event_queue.put(None)  # Сигнал для остановки
        self._processor_thread.join(timeout=5)
        self._executor.shutdown(wait=True)
    
    def _process_events(self) -> None:
        """Обработчик очереди событий (работает в отдельном потоке)"""
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)
                if event is None:  # Сигнал остановки
                    break
                
                self._emit_async(event)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Ошибка при обработке события: {e}", exc_info=True)
    
    def _emit_sync(self, event: Event) -> None:
        """Синхронная отправка события"""
        with self._lock:
            subscribers = self._get_active_subscribers(event.name)
        
        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception as e:
                logger.error(f"Ошибка при обработке события '{event.name}': {e}", exc_info=True)
    
    def _emit_async(self, event: Event) -> None:
        """Асинхронная отправка события"""
        with self._lock:
            subscribers = self._get_active_subscribers(event.name)
        
        for subscriber in subscribers:
            self._executor.submit(self._safe_call, subscriber, event)
    
    def _safe_call(self, callback: Callable, event: Event) -> None:
        """Безопасный вызов обработчика"""
        try:
            callback(event)
        except Exception as e:
            logger.error(f"Ошибка при обработке события '{event.name}': {e}", exc_info=True)
    
    def _get_active_subscribers(self, event_name: str) -> List[Callable]:
        """Получить список активных подписчиков"""
        if event_name not in self._subscribers:
            return []
        
        active_subscribers = []
        dead_refs = []
        
        for ref in self._subscribers[event_name]:
            if isinstance(ref, weakref.ref):
                callback = ref()
                if callback is not None:
                    active_subscribers.append(callback)
                else:
                    dead_refs.append(ref)
            else:
                # Сильная ссылка
                active_subscribers.append(ref)
        
        # Очистка мертвых ссылок
        if dead_refs:
            for dead_ref in dead_refs:
                self._subscribers[event_name].remove(dead_ref)
        
        return active_subscribers
    
    def _create_cleanup_callback(self, event_name: str):
        """Создать callback для очистки мертвых ссылок"""
        def cleanup(weak_ref):
            with self._lock:
                if event_name in self._subscribers:
                    try:
                        self._subscribers[event_name].remove(weak_ref)
                        if not self._subscribers[event_name]:
                            del self._subscribers[event_name]
                    except ValueError:
                        pass
        return cleanup
    
    def _is_same_callback(self, ref: Any, callback: Callable) -> bool:
        """Проверить, указывает ли ссылка на тот же callback"""
        if isinstance(ref, weakref.ref):
            return ref() is callback
        else:
            return ref is callback


# Глобальный экземпляр для удобства использования
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Получить глобальный экземпляр EventBus"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def shutdown_event_bus() -> None:
    """Остановить глобальный EventBus"""
    global _global_event_bus
    if _global_event_bus is not None:
        _global_event_bus.shutdown()
        _global_event_bus = None


# Удобные алиасы для быстрого доступа
def subscribe(event_name: str, callback: Callable, weak: bool = True) -> None:
    """Подписаться на событие через глобальный EventBus"""
    get_event_bus().subscribe(event_name, callback, weak)


def unsubscribe(event_name: str, callback: Callable) -> None:
    """Отписаться от события через глобальный EventBus"""
    get_event_bus().unsubscribe(event_name, callback)


def emit(event_name: str, data: Any = None, sync: bool = False) -> None:
    """Отправить событие через глобальный EventBus"""
    get_event_bus().emit(event_name, data, sync)


def emit_and_wait(event_name: str, data: Any = None, timeout: float = 5.0) -> List[Any]:
    """Отправить событие и дождаться результатов через глобальный EventBus"""
    return get_event_bus().emit_and_wait(event_name, data, timeout)


# Определение имен событий для типобезопасности
class Events:
    """Константы с именами событий"""
    
    # UI события
    SEND_MESSAGE = "send_message"
    CLEAR_CHAT = "clear_chat"
    LOAD_HISTORY = "load_history"
    UPDATE_TOKEN_COUNT = "update_token_count"
    UPDATE_STATUS = "update_status"
    UPDATE_DEBUG_INFO = "update_debug_info"
    
    # Настройки
    SAVE_SETTING = "save_setting"
    GET_SETTING = "get_setting"
    LOAD_SETTINGS = "load_settings"
    
    # Работа с изображениями
    ATTACH_IMAGES = "attach_images"
    STAGE_IMAGE = "stage_image"
    CLEAR_STAGED_IMAGES = "clear_staged_images"
    CAPTURE_SCREEN = "capture_screen"
    GET_CAMERA_FRAMES = "get_camera_frames"
    
    # Голосовые модели
    SELECT_VOICE_MODEL = "select_voice_model"
    INIT_VOICE_MODEL = "init_voice_model"
    CHECK_MODEL_INSTALLED = "check_model_installed"
    CHECK_MODEL_INITIALIZED = "check_model_initialized"
    CHANGE_VOICE_LANGUAGE = "change_voice_language"
    REFRESH_VOICE_MODULES = "refresh_voice_modules"
    
    # Статусы
    GET_CONNECTION_STATUS = "get_connection_status"
    GET_SILERO_STATUS = "get_silero_status"
    GET_MIC_STATUS = "get_mic_status"
    GET_SCREEN_CAPTURE_STATUS = "get_screen_capture_status"
    GET_CAMERA_CAPTURE_STATUS = "get_camera_capture_status"
    
    # Управление потоками
    STOP_SCREEN_CAPTURE = "stop_screen_capture"
    STOP_CAMERA_CAPTURE = "stop_camera_capture"
    DELETE_SOUND_FILES = "delete_sound_files"
    STOP_SERVER = "stop_server"
    
    # История чата
    GET_CHAT_HISTORY = "get_chat_history"
    LOAD_MORE_HISTORY = "load_more_history"
    
    # Mita статус
    SHOW_MITA_THINKING = "show_mita_thinking"
    SHOW_MITA_ERROR = "show_mita_error"
    HIDE_MITA_STATUS = "hide_mita_status"
    PULSE_MITA_ERROR = "pulse_mita_error"
    
    # Telegram
    REQUEST_TG_CODE = "request_tg_code"
    REQUEST_TG_PASSWORD = "request_tg_password"
    
    # G4F
    SCHEDULE_G4F_UPDATE = "schedule_g4f_update"
    
    # Разное
    CHECK_TEXT_TO_TALK = "check_text_to_talk"
    GET_CHARACTER_NAME = "get_character_name"
    GET_CURRENT_CONTEXT_TOKENS = "get_current_context_tokens"
    CALCULATE_COST = "calculate_cost"

        # Персонажи
    GET_ALL_CHARACTERS = "get_all_characters"
    GET_CURRENT_CHARACTER = "get_current_character"
    SET_CHARACTER_TO_CHANGE = "set_character_to_change"
    CHECK_CHANGE_CHARACTER = "check_change_character"
    GET_CHARACTER = "get_character"
    RELOAD_CHARACTER_DATA = "reload_character_data"
    RELOAD_CHARACTER_PROMPTS = "reload_character_prompts"
    CLEAR_CHARACTER_HISTORY = "clear_character_history"
    CLEAR_ALL_HISTORIES = "clear_all_histories"
    
    # Микрофон и речь
    SET_MICROPHONE = "set_microphone"
    START_SPEECH_RECOGNITION = "start_speech_recognition"
    STOP_SPEECH_RECOGNITION = "stop_speech_recognition"
    UPDATE_SPEECH_SETTINGS = "update_speech_settings"
    
    # Асинхронные операции
    GET_EVENT_LOOP = "get_event_loop"
    RELOAD_PROMPTS_ASYNC = "reload_prompts_async"
    
    # Загрузка
    SHOW_LOADING_POPUP = "show_loading_popup"
    CLOSE_LOADING_POPUP = "close_loading_popup"