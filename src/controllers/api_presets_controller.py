# src/controllers/api_presets_controller.py
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field

from core.events import get_event_bus, Events, Event
from main_logger import logger

from utils import _
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
class ApiTemplate:
    id: int
    name: str
    pricing: str = "mixed"
    url: str = ""
    url_tpl: str = ""
    default_model: str = ""
    known_models: List[str] = field(default_factory=list)
    gemini_case: Optional[bool] = None  # None => включаем переключатель на уровне пресета
    use_request: bool = False
    is_g4f: bool = False
    test_url: str = ""
    filter_fn: str = ""
    add_key: bool = False
    documentation_url: str = ""
    models_url: str = ""
    key_url: str = ""


@dataclass
class UserPreset:
    id: int
    name: str
    base: Optional[int] = None           # id шаблона или None, если пресет полностью ручной
    pricing: str = "mixed"
    default_model: str = ""              # если пусто — берём из шаблона
    url: str = ""                        # используется только когда base is None
    key: str = ""
    reserve_keys: List[str] = field(default_factory=list)
    gemini_case_override: Optional[bool] = None  # актуально только если в шаблоне gemini_case == None


class ApiPresetsController:
    def __init__(self):
        self.event_bus = get_event_bus()

        # Новые раздельные файлы
        self.templates_path = Path("Settings/api_templates.json")
        self.presets_path = Path("Settings/api_presets.json")

        # Старый файл для миграции
        self.legacy_path = Path("Settings/presets.json")

        self.templates: Dict[int, ApiTemplate] = {}
        self.presets: Dict[int, UserPreset] = {}
        self.presets_order: List[int] = []

        self.current_preset_id: Optional[int] = None

        # Транзиентные состояния (UI-снапшоты)
        self.preset_states: Dict[int, Dict[str, Any]] = {}

        self._load_data()
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

    # ---------- Загрузка/сохранение ----------

    def _load_data(self):
        if self.templates_path.exists() or self.presets_path.exists():
            self._load_from_new_files()
            return

        # Миграция со старого формата (Settings/presets.json)
        if self.legacy_path.exists():
            self._migrate_from_legacy()
            return

        # Чистая установка — берём дефолты из кода
        self._create_default_data()

    def _load_from_new_files(self):
        try:
            if self.templates_path.exists():
                with open(self.templates_path, 'r', encoding='utf-8') as f:
                    tdata = json.load(f)
                self.templates = {int(k): ApiTemplate(**v) for k, v in tdata.get('templates', {}).items()}
            else:
                self.templates = {}
            if self.presets_path.exists():
                with open(self.presets_path, 'r', encoding='utf-8') as f:
                    pdata = json.load(f)
                self.presets = {int(k): UserPreset(**v) for k, v in pdata.get('presets', {}).items()}
                self.presets_order = pdata.get('order', list(self.presets.keys()))
            else:
                self.presets = {}
                self.presets_order = []
            logger.info(f"Loaded {len(self.templates)} templates and {len(self.presets)} user presets")
        except Exception as e:
            logger.error(f"Failed to load new preset data: {e}", exc_info=True)
            self._create_default_data()

    def _migrate_from_legacy(self):
        try:
            with open(self.legacy_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # builtin -> templates
            self.templates = {}
            for _, preset_data in data.get('builtin', {}).items():
                # переносим только поля шаблона
                tpl = ApiTemplate(
                    id=preset_data['id'],
                    name=preset_data['name'],
                    pricing=preset_data.get('pricing', 'mixed'),
                    url=preset_data.get('url', ""),
                    url_tpl=preset_data.get('url_tpl', ""),
                    default_model=preset_data.get('default_model', ""),
                    known_models=preset_data.get('known_models', []) or [],
                    gemini_case=preset_data.get('gemini_case'),
                    use_request=preset_data.get('use_request', False),
                    is_g4f=preset_data.get('is_g4f', False),
                    test_url=preset_data.get('test_url', ""),
                    filter_fn=preset_data.get('filter_fn', ""),
                    add_key=preset_data.get('add_key', False),
                    documentation_url=preset_data.get('documentation_url', ""),
                    models_url=preset_data.get('models_url', ""),
                    key_url=preset_data.get('key_url', "")
                )
                self.templates[tpl.id] = tpl

            # custom -> presets (минимальная модель пользователя)
            self.presets = {}
            for _, preset_data in data.get('custom', {}).items():
                base = preset_data.get('base')
                up = UserPreset(
                    id=preset_data['id'],
                    name=preset_data['name'],
                    base=base,
                    pricing=preset_data.get('pricing', 'mixed'),
                    default_model=preset_data.get('default_model', ""),
                    url=preset_data.get('url', "") if base is None else "",
                    key=preset_data.get('key', ""),
                    reserve_keys=preset_data.get('reserve_keys', []) or []
                )
                # переносим кастомные модели в шаблон (если были)
                km = preset_data.get('known_models', [])
                if km and base and base in self.templates:
                    t = self.templates[base]
                    merged = sorted(list(set((t.known_models or []) + km)), reverse=True)
                    t.known_models = merged
                self.presets[up.id] = up

            self.presets_order = data.get('custom_order', list(self.presets.keys()))
            self._save_templates()
            self._save_presets()
            logger.info(f"Migrated legacy presets to separate templates/presets files. "
                        f"Templates: {len(self.templates)}, Presets: {len(self.presets)}")
        except Exception as e:
            logger.error(f"Failed to migrate legacy presets: {e}", exc_info=True)
            self._create_default_data()

    def _create_default_data(self):
        from presets.api_templates import API_TEMPLATES_DATA
        from presets.api_presets import DEFAULT_USER_PRESETS

        self.templates = {p['id']: ApiTemplate(**p) for p in API_TEMPLATES_DATA}
        self.presets = {p['id']: UserPreset(**p) for p in DEFAULT_USER_PRESETS}
        self.presets_order = list(self.presets.keys())

        self._save_templates()
        self._save_presets()
        logger.info("Created default templates and presets")

    def _save_templates(self):
        os.makedirs("Settings", exist_ok=True)
        data = {'templates': {str(t.id): asdict(t) for t in self.templates.values()}}
        with open(self.templates_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save_presets(self):
        os.makedirs("Settings", exist_ok=True)
        data = {
            'presets': {str(p.id): asdict(p) for p in self.presets.values()},
            'order': self.presets_order
        }
        with open(self.presets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _generate_new_id(self) -> int:
        all_ids = set(self.templates.keys()) | set(self.presets.keys())
        return max(all_ids, default=1000) + 1

    # ---------- Хелперы ----------

    def _build_effective_preset_dict(self, preset_id: int) -> Optional[Dict[str, Any]]:
        if preset_id in self.templates:
            # Запрашивают сам шаблон
            return asdict(self.templates[preset_id])

        p = self.presets.get(preset_id)
        if not p:
            return None

        tpl = self.templates.get(p.base) if p.base else None

        result = {
            'id': p.id,
            'name': p.name,
            'pricing': (tpl.pricing if tpl else p.pricing),
            'base': p.base,
            # ВАЖНО: если пресет от шаблона и у шаблона есть прямой url — отдать его сразу
            'url': p.url if not tpl else (tpl.url if tpl and tpl.url else ""),
            'url_tpl': tpl.url_tpl if tpl else "",
            'add_key': tpl.add_key if tpl else False,
            'default_model': p.default_model or (tpl.default_model if tpl else ""),
            'known_models': (tpl.known_models if tpl else []),
            'gemini_case': (tpl.gemini_case if tpl else None),
            'use_request': tpl.use_request if tpl is not None else True,
            'is_g4f': tpl.is_g4f if tpl else False,
            'test_url': tpl.test_url if tpl else "",
            'filter_fn': tpl.filter_fn if tpl else "",
            'documentation_url': tpl.documentation_url if tpl else "",
            'models_url': tpl.models_url if tpl else "",
            'key_url': tpl.key_url if tpl else "",
            # Секреты/резервы — из пресета
            'key': p.key,
            'reserve_keys': p.reserve_keys or [],
        }
        return result

    # ---------- Обработчики событий ----------

    def _on_get_preset_list(self, event: Event):
        meta = {
            'builtin': [],
            'custom': []
        }
        # builtin = шаблоны
        for tpl in self.templates.values():
            meta['builtin'].append(PresetMeta(
                id=tpl.id,
                name=tpl.name,
                pricing=tpl.pricing,
                is_g4f=tpl.is_g4f,
                gemini_case=tpl.gemini_case
            ))

        # custom = пользовательские пресеты (поля берём из шаблона при наличии)
        ordered_custom = []
        for pid in self.presets_order:
            if pid in self.presets:
                ordered_custom.append(self.presets[pid])
        for pid, up in self.presets.items():
            if pid not in self.presets_order:
                ordered_custom.append(up)
                self.presets_order.append(pid)

        for up in ordered_custom:
            tpl = self.templates.get(up.base) if up.base else None
            meta['custom'].append(PresetMeta(
                id=up.id,
                name=up.name,
                pricing=(tpl.pricing if tpl else up.pricing),
                is_g4f=(tpl.is_g4f if tpl else False),
                gemini_case=(tpl.gemini_case if tpl else None)
            ))
        return meta
    
    def _on_get_preset_full(self, event: Event):
        preset_id = event.data.get('id')
        data = self._build_effective_preset_dict(preset_id)
        return data

    def _on_save_custom_preset(self, event: Event):
        data = event.data.get('data') or {}
        preset_id = data.get('id')
        if preset_id is None:
            preset_id = self._generate_new_id()
            data['id'] = preset_id

        base = data.get('base')
        name = data.get('name') or f"Preset {preset_id}"

        up = self.presets.get(preset_id) or UserPreset(id=preset_id, name=name)
        up.name = name
        up.base = base
        up.pricing = data.get('pricing', up.pricing)
        up.default_model = data.get('default_model', up.default_model)
        # url храним только если base отсутствует
        up.url = data.get('url', up.url) if not base else ""
        up.key = data.get('key', up.key)
        up.reserve_keys = data.get('reserve_keys', up.reserve_keys) or up.reserve_keys

        self.presets[preset_id] = up
        if preset_id not in self.presets_order:
            self.presets_order.append(preset_id)

        self._save_presets()

        self.event_bus.emit(Events.ApiPresets.PRESET_SAVED, {'id': preset_id})
        return preset_id
    
    def _on_delete_custom_preset(self, event: Event):
        preset_id = event.data.get('id')
        if preset_id in self.presets:
            del self.presets[preset_id]
            if preset_id in self.preset_states:
                del self.preset_states[preset_id]
            if preset_id in self.presets_order:
                self.presets_order.remove(preset_id)
            self._save_presets()
            self.event_bus.emit(Events.ApiPresets.PRESET_DELETED, {'id': preset_id})
            return True
        return False
    
    def _on_save_presets_order(self, event: Event):
        order = event.data.get('order', [])
        if order:
            self.presets_order = order
            self._save_presets()
            return True
        return False
    
    def _on_export_preset(self, event: Event):
        preset_id = event.data.get('id')
        path = event.data.get('path')

        # экспортируем «эффективный» словарь (чтобы вне системы он был самодостаточен)
        preset_dict = self._build_effective_preset_dict(preset_id)
        if not preset_dict:
            return False

        state = self.preset_states.get(preset_id, {})
        if state:
            preset_dict.update(state)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(preset_dict, f, indent=2, ensure_ascii=False)
        return True
    
    def _on_import_preset(self, event: Event):
        path = event.data.get('path')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # поддержим импорт старого полноформатного пресета
            new_id = self._generate_new_id()
            base = data.get('base')
            up = UserPreset(
                id=new_id,
                name=data.get('name', f"Preset {new_id}"),
                base=base,
                pricing=data.get('pricing', 'mixed'),
                default_model=data.get('default_model', ''),
                url=data.get('url', '') if not base else '',
                key=data.get('key', ''),
                reserve_keys=data.get('reserve_keys', []) or []
            )
            self.presets[new_id] = up
            self.presets_order.append(new_id)
            self._save_presets()

            # Секреты/состояния (напр., key) уже положили в пресет. Но поддержим state для совместимости
            if 'key' in data:
                self.preset_states[new_id] = {'key': data['key']}

            self.event_bus.emit(Events.ApiPresets.PRESET_IMPORTED, {'id': new_id})
            return new_id
        except Exception as e:
            logger.error(f"Failed to import preset: {e}")
            return None
    
    def _on_test_connection(self, event: Event):
        preset_id = event.data.get('id')
        base_id = event.data.get('base')
        key = event.data.get('key', '')

        p_tpl: Optional[ApiTemplate] = None

        # приоритет: явно указанный шаблон -> шаблон пресета -> ничего
        if base_id:
            p_tpl = self.templates.get(base_id)
        elif preset_id and preset_id in self.presets:
            up = self.presets[preset_id]
            if up.base and up.base in self.templates:
                p_tpl = self.templates[up.base]
        elif preset_id and preset_id in self.templates:
            p_tpl = self.templates[preset_id]

        if not p_tpl or not p_tpl.test_url:
            logger.warning(f"No test_url for preset {preset_id} and base {base_id}")
            self.event_bus.emit(Events.ApiPresets.TEST_FAILED, {
                'id': preset_id,
                'error': 'no_test_url',
                'message': _("URL для тестирования не найден", "Test URL not found")
            })
            return
        
        test_url = p_tpl.test_url.replace('{key}', key)
        logger.info(f"Starting sync test connection for preset {preset_id} to {test_url}")
        
        threading.Thread(target=self._sync_test_connection, 
                         args=(preset_id, test_url, p_tpl.filter_fn)).start()

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
        if not new_models:
            return False

        # Если это кастом — обновляем его базовый шаблон.
        if preset_id in self.presets:
            up = self.presets[preset_id]
            if up.base and up.base in self.templates:
                tpl = self.templates[up.base]
                existing = set(tpl.known_models or [])
                updated = list(existing.union(set(new_models)))
                updated.sort(reverse=True)
                tpl.known_models = updated
                self._save_templates()
                logger.info(f"Updated base template {up.base} with sorted models")
                return True
            return False

        # Если это сам шаблон — обновляем его
        if preset_id in self.templates:
            tpl = self.templates[preset_id]
            existing = set(tpl.known_models or [])
            updated = list(existing.union(set(new_models)))
            updated.sort(reverse=True)
            tpl.known_models = updated
            self._save_templates()
            logger.info(f"Updated and sorted models for template {preset_id}")
            return True

        return False

    def _on_set_gemini_case(self, event: Event):
        preset_id = event.data.get('id')
        value = event.data.get('value')
        # Вкл/выкл логики Gemini запоминаем в пресете, но только если шаблон разрешает (gemini_case=None)
        up = self.presets.get(preset_id)
        if not up:
            return False
        tpl = self.templates.get(up.base) if up.base else None
        if tpl and tpl.gemini_case is None:
            up.gemini_case_override = bool(value)
            self._save_presets()
            return True
        return False
    
    def _on_save_preset_state(self, event: Event):
        preset_id = event.data.get('id')
        state = event.data.get('state') or {}
        if not preset_id or not state:
            return False

        # Обновляем «живые» поля пресета (persist)
        if preset_id in self.presets:
            up = self.presets[preset_id]
            if 'key' in state:
                up.key = state['key']
            if 'model' in state:
                up.default_model = state['model']
            if 'url' in state and not up.base:
                up.url = state['url']
            if 'gemini_case' in state:
                up.gemini_case_override = bool(state['gemini_case'])
            self._save_presets()

        # Параллельно держим снапшот state для UI
        self.preset_states[preset_id] = state
        return True
    
    def _on_load_preset_state(self, event: Event):
        preset_id = event.data.get('id')
        state = self.preset_states.get(preset_id, {})
        return state
    
    def _on_get_current_preset_id(self, event: Event):
        return self.current_preset_id
    
    def _on_set_current_preset_id(self, event: Event):
        self.current_preset_id = event.data.get('id')
        return True