from handlers.chat_handler import ChatModel
from main_logger import logger
import importlib
import sys
import os
import functools
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox
from utils import _

class ModelController:
    def __init__(self, main_controller, api_key, api_key_res, api_url, api_model, makeRequest, pip_installer):
        self.main = main_controller
        self.model = ChatModel(self.main, api_key, api_key_res, api_url, api_model, makeRequest, pip_installer)
        