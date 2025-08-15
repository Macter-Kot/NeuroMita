import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

from core.events import get_event_bus, Events, Event
from main_logger import logger

import threading
import requests


@dataclass
class PresetMeta:
    id: int
    name: str
    pricing: str
    is_g4f: bool = False
    gemini_case: Optional[bool] = None


@dataclass
class ApiPreset:
    id: int
    name: str
    pricing: str = "mixed"
    url: str = ""
    url_tpl: str = ""
    default_model: str = ""
    known_models: List[str] = None
    gemini_case: Optional[bool] = None
    use_request: bool = False
    is_g4f: bool = False
    test_url: str = ""
    filter_fn: str = ""
    base: Optional[int] = None
    add_key: bool = False
    help_url: str = ""
    key: str = ""
    reserve_keys: List[str] = None
    
    def __post_init__(self):
        if self.known_models is None:
            self.known_models = []
        if self.reserve_keys is None:
            self.reserve_keys = []


class ApiPresetsController:
    def __init__(self):
        self.event_bus = get_event_bus()
        self.presets_path = Path("Settings/presets.json")
        self.builtin_presets: Dict[int, ApiPreset] = {}
        self.custom_presets: Dict[int, ApiPreset] = {}
        self.custom_presets_order: List[int] = []
        self.current_preset_id: Optional[int] = None
        self.preset_states: Dict[int, Dict[str, Any]] = {}
        
        self._load_presets()
        self._subscribe_to_events()
    
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.ApiPresets.GET_PRESET_LIST, self._on_get_preset_list, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.GET_PRESET_FULL, self._on_get_preset_full, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.SAVE_CUSTOM_PRESET, self._on_save_custom_preset, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.DELETE_CUSTOM_PRESET, self._on_delete_custom_preset, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.EXPORT_PRESET, self._on_export_preset, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.IMPORT_PRESET, self._on_import_preset, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.TEST_CONNECTION, self._on_test_connection, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.SET_GEMINI_CASE, self._on_set_gemini_case, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.SAVE_PRESET_STATE, self._on_save_preset_state, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.LOAD_PRESET_STATE, self._on_load_preset_state, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.GET_CURRENT_PRESET_ID, self._on_get_current_preset_id, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.SET_CURRENT_PRESET_ID, self._on_set_current_preset_id, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.UPDATE_PRESET_MODELS, self._on_update_preset_models, weak=False)
        self.event_bus.subscribe(Events.ApiPresets.SAVE_PRESETS_ORDER, self._on_save_presets_order, weak=False)
    
    def _load_presets(self):
        if self.presets_path.exists():
            try:
                with open(self.presets_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for id_str, preset_data in data.get('builtin', {}).items():
                    preset = ApiPreset(**preset_data)
                    self.builtin_presets[preset.id] = preset
                
                for id_str, preset_data in data.get('custom', {}).items():
                    preset = ApiPreset(**preset_data)
                    self.custom_presets[preset.id] = preset
                
                self.custom_presets_order = data.get('custom_order', list(self.custom_presets.keys()))
                    
                logger.info(f"Loaded {len(self.builtin_presets)} builtin and {len(self.custom_presets)} custom presets")
            except Exception as e:
                logger.error(f"Failed to load presets: {e}")
                self._create_default_presets()
        else:
            self._create_default_presets()
    
    def _create_default_presets(self):
        from presets.api_presets import API_PRESETS_DATA
        self.builtin_presets = {}
        for preset_data in API_PRESETS_DATA:
            preset = ApiPreset(**preset_data)
            self.builtin_presets[preset.id] = preset
        self._save_presets()
        logger.info("Created default presets")
    
    def _save_presets(self):
        os.makedirs("Settings", exist_ok=True)
        
        data = {
            'builtin': {str(p.id): asdict(p) for p in self.builtin_presets.values()},
            'custom': {str(p.id): asdict(p) for p in self.custom_presets.values()},
            'custom_order': self.custom_presets_order
        }
        
        with open(self.presets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _get_all_presets(self) -> Dict[int, ApiPreset]:
        all_presets = {}
        all_presets.update(self.builtin_presets)
        all_presets.update(self.custom_presets)
        return all_presets
    
    def _generate_new_id(self) -> int:
        all_ids = set(self.builtin_presets.keys()) | set(self.custom_presets.keys())
        return max(all_ids, default=1000) + 1
    
    def _on_get_preset_list(self, event: Event):
        meta = {
            'builtin': [],
            'custom': []
        }
        
        for preset in self.builtin_presets.values():
            meta['builtin'].append(PresetMeta(
                id=preset.id,
                name=preset.name,
                pricing=preset.pricing,
                is_g4f=preset.is_g4f,
                gemini_case=preset.gemini_case
            ))
        
        ordered_custom_presets = []
        for preset_id in self.custom_presets_order:
            if preset_id in self.custom_presets:
                ordered_custom_presets.append(self.custom_presets[preset_id])
        
        for preset_id in self.custom_presets:
            if preset_id not in self.custom_presets_order:
                ordered_custom_presets.append(self.custom_presets[preset_id])
                self.custom_presets_order.append(preset_id)
        
        for preset in ordered_custom_presets:
            meta['custom'].append(PresetMeta(
                id=preset.id,
                name=preset.name,
                pricing=preset.pricing,
                is_g4f=preset.is_g4f,
                gemini_case=preset.gemini_case
            ))
        
        return meta
    
    def _on_get_preset_full(self, event: Event):
        preset_id = event.data.get('id')
        if preset_id in self.builtin_presets:
            return asdict(self.builtin_presets[preset_id])
        elif preset_id in self.custom_presets:
            return asdict(self.custom_presets[preset_id])
        return None
    
    def _on_save_custom_preset(self, event: Event):
        data = event.data.get('data')
        preset_id = data.get('id')
        
        if preset_id is None:
            preset_id = self._generate_new_id()
            data['id'] = preset_id
        
        if 'base' in data and data['base']:
            base_preset = self._get_all_presets().get(data['base'])
            if base_preset and base_preset.gemini_case is None:
                if 'gemini_case' not in data:
                    data['gemini_case'] = None
        
        preset = ApiPreset(**data)
        self.custom_presets[preset_id] = preset
        
        if preset_id not in self.custom_presets_order:
            self.custom_presets_order.append(preset_id)
        
        self._save_presets()
        
        self.event_bus.emit(Events.ApiPresets.PRESET_SAVED, {'id': preset_id})
        return preset_id
    
    def _on_delete_custom_preset(self, event: Event):
        preset_id = event.data.get('id')
        
        if preset_id in self.custom_presets:
            del self.custom_presets[preset_id]
            if preset_id in self.preset_states:
                del self.preset_states[preset_id]
            if preset_id in self.custom_presets_order:
                self.custom_presets_order.remove(preset_id)
            self._save_presets()
            self.event_bus.emit(Events.ApiPresets.PRESET_DELETED, {'id': preset_id})
            return True
        return False
    
    def _on_save_presets_order(self, event: Event):
        order = event.data.get('order', [])
        if order:
            self.custom_presets_order = order
            self._save_presets()
            return True
        return False
    
    def _on_export_preset(self, event: Event):
        preset_id = event.data.get('id')
        path = event.data.get('path')
        
        preset = None
        if preset_id in self.builtin_presets:
            preset = self.builtin_presets[preset_id]
        elif preset_id in self.custom_presets:
            preset = self.custom_presets[preset_id]
        
        if preset:
            preset_dict = asdict(preset)
            state = self.preset_states.get(preset_id, {})
            if state:
                preset_dict.update(state)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(preset_dict, f, indent=2, ensure_ascii=False)
            return True
        return False
    
    def _on_import_preset(self, event: Event):
        path = event.data.get('path')
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            data['id'] = self._generate_new_id()
            preset = ApiPreset(**data)
            self.custom_presets[preset.id] = preset
            self.custom_presets_order.append(preset.id)
            self._save_presets()
            
            if 'key' in data:
                self.preset_states[preset.id] = {'key': data['key']}
            
            self.event_bus.emit(Events.ApiPresets.PRESET_IMPORTED, {'id': preset.id})
            return preset.id
        except Exception as e:
            logger.error(f"Failed to import preset: {e}")
            return None
    
    def _on_test_connection(self, event: Event):
        preset_id = event.data.get('id')
        key = event.data.get('key', '')
        p = self._get_all_presets().get(preset_id)
        if not p or not p.test_url:
            logger.warning(f"No test_url for preset {preset_id}")
            return
        test_url = p.test_url.replace('{key}', key)
        logger.info(f"Starting sync test connection for preset {preset_id} to {test_url}")
        
        threading.Thread(target=self._sync_test_connection, args=(preset_id, test_url, p.filter_fn)).start()

    def _sync_test_connection(self, preset_id: int, url: str, filter_fn: str):
        try:
            resp = requests.get(url, timeout=10)
            status = resp.status_code
            text = resp.text
            success = False
            message = ""
            models = []
            if status == 200:
                try:
                    data = json.loads(text)
                    if filter_fn:
                        from utils.api_filters import apply_filter
                        data = apply_filter(filter_fn, data)
                    if 'models' in data:
                        models = [m.get('name', '').split('/')[-1] for m in data.get('models', []) if m.get('name')]
                        success = True
                        message = f"Found {len(models)} models"
                    else:
                        success = True
                        message = "Connection successful"
                except Exception as e:
                    success = False
                    message = f"Parsing error: {str(e)}"
                    logger.error(f"Test parsing error: {e}")
            elif status == 403:
                message = "Invalid API key"
            elif status == 400:
                message = "Bad request"
            else:
                message = f"HTTP {status}"
            
            logger.info(f"Test result for {preset_id}: success={success}, message={message}, models={len(models)}")
            self.event_bus.emit(Events.ApiPresets.TEST_RESULT, {
                'id': preset_id,
                'success': success,
                'message': message,
                'models': models
            })
        except requests.Timeout:
            logger.warning(f"Test timeout for {preset_id}")
            self.event_bus.emit(Events.ApiPresets.TEST_RESULT, {
                'id': preset_id,
                'success': False,
                'message': "Connection timeout"
            })
        except Exception as e:
            logger.error(f"Test error for {preset_id}: {e}")
            self.event_bus.emit(Events.ApiPresets.TEST_RESULT, {
                'id': preset_id,
                'success': False,
                'message': str(e)
            })

    def _on_update_preset_models(self, event: Event):
        preset_id = event.data.get('id')
        new_models = event.data.get('models', [])
        
        if preset_id in self.builtin_presets:
            preset = self.builtin_presets[preset_id]
        elif preset_id in self.custom_presets:
            preset = self.custom_presets[preset_id]
        else:
            return False
        
        existing = set(preset.known_models)
        updated = list(existing.union(set(new_models)))
        
        updated.sort(reverse=True)
        
        preset.known_models = updated
        
        base_id = preset.base
        if base_id is not None:
            base_preset = self._get_all_presets().get(base_id)
            if base_preset:
                base_existing = set(base_preset.known_models)
                base_updated = list(base_existing.union(set(new_models)))
                base_updated.sort(reverse=True)
                base_preset.known_models = base_updated
                logger.info(f"Updated base preset {base_id} with sorted models")
        
        self._save_presets()
        logger.info(f"Updated and sorted models for preset {preset_id}")
        return True

    def _on_set_gemini_case(self, event: Event):
        preset_id = event.data.get('id')
        value = event.data.get('value')
        
        if preset_id in self.custom_presets:
            preset = self.custom_presets[preset_id]
            if preset.gemini_case is None:
                preset.gemini_case = value
                self._save_presets()
                return True
        return False
    
    def _on_save_preset_state(self, event: Event):
        preset_id = event.data.get('id')
        state = event.data.get('state')
        
        if preset_id and state:
            if 'key' in state:
                self.preset_states[preset_id] = state
                return True
        return False
    
    def _on_load_preset_state(self, event: Event):
        preset_id = event.data.get('id')
        state = self.preset_states.get(preset_id, {})
        return state
    
    def _on_get_current_preset_id(self, event: Event):
        return self.current_preset_id
    
    def _on_set_current_preset_id(self, event: Event):
        self.current_preset_id = event.data.get('id')
        return True