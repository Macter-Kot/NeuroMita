import asyncio
from typing import Optional
import numpy as np
from handlers.asr_models.speech_recognizer_base import SpeechRecognizerInterface
from utils import getTranslationVariant as _

class GoogleRecognizer(SpeechRecognizerInterface):
    def __init__(self, pip_installer, logger):
        super().__init__(pip_installer, logger)
        self._sr = None
        
    async def install(self) -> bool:
        try:
            import speech_recognition as sr
        except ImportError:
            self.logger.info("Библиотека 'SpeechRecognition' не найдена, попытка установки...")
            if self.pip_installer.install_package("SpeechRecognition", description="Установка SpeechRecognition..."):
                try:
                    import speech_recognition as sr
                except ImportError:
                    self.logger.critical("Не удалось импортировать 'SpeechRecognition' даже после установки.")
                    return False
            else:
                self.logger.critical("Не удалось установить 'SpeechRecognition'.")
                return False
        
        self._sr = sr
        return True
    
    async def init(self, **kwargs) -> bool:
        if self._sr is None:
            return False
        self._is_initialized = True
        return True
    
    async def transcribe(self, audio_data: np.ndarray, sample_rate: int) -> Optional[str]:
        if not self._is_initialized:
            return None
            
        recognizer = self._sr.Recognizer()
        audio_data_int16 = (audio_data * 32767).astype(np.int16)
        
        audio = self._sr.AudioData(
            audio_data_int16.tobytes(),
            sample_rate=sample_rate,
            sample_width=2
        )
        
        try:
            text = recognizer.recognize_google(audio, language="ru-RU")
            return text
        except self._sr.UnknownValueError:
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при распознавании Google: {e}")
            return None
    
    def _check_microphone_permissions(self, microphone_index):
        """Проверить доступность микрофона и разрешения"""
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            
            try:
                # Получаем информацию о устройстве
                device_info = pa.get_device_info_by_index(microphone_index)
                
                # Проверяем, что устройство поддерживает ввод
                if device_info['maxInputChannels'] == 0:
                    return False, "Выбранное устройство не поддерживает аудио ввод"
                
                # Пробуем создать тестовый поток для проверки разрешений
                try:
                    test_stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=int(device_info['defaultSampleRate']),
                        input=True,
                        input_device_index=microphone_index,
                        frames_per_buffer=1024
                    )
                    test_stream.close()
                    return True, "OK"
                    
                except Exception as stream_error:
                    error_msg = str(stream_error).lower()
                    if "invalid device" in error_msg:
                        return False, "Устройство недоступно или отключено"
                    elif "unanticipated host error" in error_msg or "access denied" in error_msg:
                        return False, "Нет разрешения на доступ к микрофону"
                    else:
                        return False, f"Ошибка доступа к микрофону: {stream_error}"
                        
            finally:
                pa.terminate()
                
        except Exception as e:
            return False, f"Ошибка проверки микрофона: {e}"
    
    async def live_recognition(self, microphone_index: int, handle_voice_callback, 
                              vad_model, active_flag, **kwargs) -> None:
        if self._sr is None:
            self.logger.error("Модуль SpeechRecognition не инициализирован")
            return

        # Проверяем список микрофонов
        try:
            mic_list = self._sr.Microphone.list_microphone_names()
            if microphone_index >= len(mic_list):
                self.logger.error(f"Индекс микрофона {microphone_index} выходит за пределы списка")
                return
                
        except Exception as e:
            self.logger.error(f"Не удалось получить список микрофонов: {e}")
            return
        
        # Проверяем разрешения на микрофон
        permissions_ok, permission_error = self._check_microphone_permissions(microphone_index)
        if not permissions_ok:
            self.logger.error(f"Проблема с доступом к микрофону: {permission_error}")
            
            # Показываем MessageBox с ошибкой
            try:
                from PyQt6.QtWidgets import QMessageBox, QApplication
                if QApplication.instance():
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Icon.Warning)
                    msg.setWindowTitle(_("Ошибка доступа к микрофону", "Microphone Access Error"))
                    
                    if "разрешени" in permission_error.lower() or "access denied" in permission_error.lower():
                        msg.setText(_("Нет разрешения на доступ к микрофону", "No permission to access microphone"))
                        msg.setInformativeText(_(
                            "Проверьте настройки конфиденциальности Windows:\n"
                            "Настройки → Конфиденциальность → Микрофон\n"
                            "Разрешите доступ к микрофону для приложений",
                            "Check Windows privacy settings:\n"
                            "Settings → Privacy → Microphone\n"
                            "Allow microphone access for applications"
                        ))
                    else:
                        msg.setText(_("Ошибка доступа к микрофону", "Microphone access error"))
                        msg.setInformativeText(permission_error)
                    
                    msg.exec()
            except:
                pass  # Если GUI недоступен, просто продолжаем
            
            return

        recognizer = self._sr.Recognizer()
        chunk_size = kwargs.get('chunk_size', 1024)
        
        # Конфигурации для попыток подключения
        configs = [
            {"sample_rate": 44100, "chunk_size": chunk_size},
            {"sample_rate": 22050, "chunk_size": chunk_size},
            {"sample_rate": 16000, "chunk_size": chunk_size},
        ]
        
        source = None
        for config in configs:
            try:
                source = self._sr.Microphone(
                    device_index=microphone_index,
                    sample_rate=config['sample_rate'],
                    chunk_size=config['chunk_size']
                )
                
                source.__enter__()
                
                if hasattr(source, 'stream') and source.stream is not None:
                    self.logger.info(f"Микрофон подключен: {mic_list[microphone_index]}")
                    break
                else:
                    source.__exit__(None, None, None)
                    source = None
                    
            except Exception as e:
                if source:
                    try:
                        source.__exit__(None, None, None)
                    except:
                        pass
                source = None
                self.logger.debug(f"Конфигурация {config} не подошла: {e}")
        
        if source is None:
            self.logger.error("Не удалось подключиться к микрофону")
            return
        
        try:
            # Быстрая настройка шума
            try:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
            except:
                pass  # Игнорируем ошибки настройки шума
            
            self.logger.info("Микрофон готов к распознаванию")
            
            # Основной цикл
            while active_flag():
                try:
                    audio = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    )
                    
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: recognizer.recognize_google(audio, language="ru-RU")
                    )
                    
                    if text and text.strip():
                        self.logger.info(f"Распознано: {text}")
                        await handle_voice_callback(text)
                        
                except self._sr.WaitTimeoutError:
                    continue
                except self._sr.UnknownValueError:
                    continue
                except self._sr.RequestError as e:
                    self.logger.error(f"Ошибка Google API: {e}")
                    await asyncio.sleep(2)
                except Exception as e:
                    self.logger.error(f"Ошибка распознавания: {e}")
                    await asyncio.sleep(1)
                    
        finally:
            if source:
                try:
                    source.__exit__(None, None, None)
                    self.logger.debug("Микрофон закрыт")
                except:
                    pass
    
    def cleanup(self) -> None:
        self._sr = None
        self._is_initialized = False