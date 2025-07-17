from handlers.chat_handler import ChatModel
from utils import _
from core.events import get_event_bus, Events, Event

class ModelController:
    def __init__(self, settings, api_key, api_key_res, api_url, api_model, makeRequest, pip_installer):
        self.event_bus = get_event_bus()
        self.model = ChatModel(settings, api_key, api_key_res, api_url, api_model, makeRequest, pip_installer)
        self._subscribe_to_events()
        
    def _subscribe_to_events(self):
        self.event_bus.subscribe("model_settings_loaded", self._on_model_settings_loaded, weak=False)
        self.event_bus.subscribe("model_setting_changed", self._on_model_setting_changed, weak=False)
        self.event_bus.subscribe("model_character_change", self._on_character_change, weak=False)
        
    def _on_model_settings_loaded(self, event: Event):
        data = event.data
        if data.get('api_key'):
            self.model.api_key = data['api_key']
        if data.get('api_url'):
            self.model.api_url = data['api_url']
        if data.get('api_model'):
            self.model.api_model = data['api_model']
        if 'makeRequest' in data:
            self.model.makeRequest = data['makeRequest']
            
        if self.model.api_key or self.model.api_url:
            self.model.update_openai_client()
            
    def _on_model_setting_changed(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key == "NM_API_MODEL":
            self.model.api_model = value.strip()
        elif key == "NM_API_KEY":
            self.model.api_key = value.strip()
            self.model.update_openai_client()
        elif key == "NM_API_URL":
            self.model.api_url = value.strip()
            self.model.update_openai_client()
        elif key == "NM_API_REQ":
            self.model.makeRequest = bool(value)
        elif key == "gpt4free_model":
            self.model.gpt4free_model = value.strip()
        elif key == "MODEL_MAX_RESPONSE_TOKENS":
            self.model.max_response_tokens = int(value)
        elif key == "MODEL_TEMPERATURE":
            self.model.temperature = float(value)
        elif key == "MODEL_PRESENCE_PENALTY":
            self.model.presence_penalty = float(value)
        elif key == "MODEL_FREQUENCY_PENALTY":
            self.model.frequency_penalty = float(value)
        elif key == "MODEL_LOG_PROBABILITY":
            self.model.log_probability = float(value)
        elif key == "MODEL_TOP_K":
            self.model.top_k = int(value)
        elif key == "MODEL_TOP_P":
            self.model.top_p = float(value)
        elif key == "MODEL_THOUGHT_PROCESS":
            self.model.thinking_budget = float(value)
        elif key == "MODEL_MESSAGE_LIMIT":
            self.model.memory_limit = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_COUNT":
            self.model.max_request_attempts = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_TIME":
            self.model.request_delay = float(value)
        elif key == "IMAGE_QUALITY_REDUCTION_ENABLED":
            self.model.image_quality_reduction_enabled = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_START_INDEX":
            self.model.image_quality_reduction_start_index = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE":
            self.model.image_quality_reduction_use_percentage = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_MIN_QUALITY":
            self.model.image_quality_reduction_min_quality = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_DECREASE_RATE":
            self.model.image_quality_reduction_decrease_rate = int(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_ON_LIMIT":
            self.model.enable_history_compression_on_limit = bool(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_PERIODIC":
            self.model.enable_history_compression_periodic = bool(value)
        elif key == "HISTORY_COMPRESSION_OUTPUT_TARGET":
            self.model.history_compression_output_target = str(value)
        elif key == "HISTORY_COMPRESSION_PERIODIC_INTERVAL":
            self.model.history_compression_periodic_interval = int(value)
        elif key == "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS":
            self.model.history_compression_min_messages_to_compress = float(value)
        elif key == "TOKEN_COST_INPUT":
            self.model.token_cost_input = float(value)
        elif key == "TOKEN_COST_OUTPUT":
            self.model.token_cost_output = float(value)
        elif key == "MAX_MODEL_TOKENS":
            self.model.max_model_tokens = int(value)
            
    def _on_character_change(self, event: Event):
        character = event.data.get('character')
        if character:
            self.model.current_character_to_change = character
            self.model.check_change_current_character()