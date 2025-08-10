from .base import BaseProvider, LLMRequest
import requests
import json
import copy
from main_logger import logger
from utils import save_combined_messages

class GeminiProvider(BaseProvider):
    name = "gemini"
    priority = 20

    def is_applicable(self, req: LLMRequest) -> bool:
        if not req.make_request:
            return False
        if not req.gemini_case:
            return False
        return True

    def generate(self, req: LLMRequest) -> str:
        return self.generate_request_gemini(req)

    def generate_request_gemini(self, req: LLMRequest) -> str:
        if req.depth > 3:
            return None

        params = {k: v for k, v in req.extra.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
        self.clear_endline_sim(params)

        self.change_last_message_to_user_for_gemini("gemini", req.messages)

        contents = []
        for msg in req.messages:
            role = "model" if msg["role"] == "assistant" else msg["role"]
            if isinstance(msg.get("content"), dict) and ("functionCall" in msg["content"] or "functionResponse" in msg["content"]):
                contents.append({"role": role, "parts": [msg["content"]]})
                continue
            if role == "system":
                role = "user"
                if isinstance(msg["content"], list):
                    msg_content = [{"type": "text", "text": "[System Prompt]:"}] + msg["content"]
                else:
                    msg_content = f"[System Prompt]: {msg['content']}"
            else:
                msg_content = msg["content"]
            contents.append({"role": role, "parts": self._format_multimodal_content_for_gemini(msg_content)})

        data = {"contents": contents, "generationConfig": params}
        if req.tools_on and req.tools_payload:
            data["tools"] = req.tools_payload

        need_stream = req.stream and "tools" not in data
        save_combined_messages(contents, "SavedMessages/last_gemini_log")

        response = requests.post(req.api_url, headers={"Content-Type": "application/json"}, json=data, stream=need_stream)
        if response.status_code != 200:
            return None
        if need_stream:
            return self._handle_gemini_stream(response, req.stream_cb)

        first_part = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0]
        func_call = first_part.get("functionCall")
        if func_call:
            name = func_call.get("name")
            args = func_call.get("args", {})
            tm = req.tool_manager
            if tm:
                tool_result = tm.run(name, args)
                from tools.manager import mk_tool_call_msg, mk_tool_resp_msg
                new_messages = copy.deepcopy(req.messages)
                new_messages.append(mk_tool_call_msg(name, args))
                new_messages.append(mk_tool_resp_msg(name, tool_result))
                req.messages = new_messages
                req.depth += 1
                return self.generate_request_gemini(req)
        return first_part.get("text", "") or "…"

    def _handle_gemini_stream(self, response, stream_callback: callable = None) -> str:
        full_response_parts = []
        json_buffer = ''
        decoder = json.JSONDecoder()
        try:
            for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                json_buffer += chunk
                while json_buffer.strip():
                    try:
                        result, index = decoder.raw_decode(json_buffer)
                        generated_text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[
                            0].get("text", "")
                        if generated_text:
                            if stream_callback:
                                stream_callback(generated_text)
                            full_response_parts.append(generated_text)
                        json_buffer = json_buffer[index:].lstrip()
                    except json.JSONDecodeError:
                        break

            full_text = "".join(full_response_parts)
            logger.info("Gemini stream finished. Full text accumulated.")
            return full_text
        except Exception as e:
            logger.error(f"Error processing Gemini stream: {e}", exc_info=True)
            return "".join(full_response_parts)

    def _format_multimodal_content_for_gemini(self, message_content):
        parts = []
        if isinstance(message_content, list):
            for item in message_content:
                if item["type"] == "text":
                    parts.append({"text": item["text"]})
                elif item["type"] == "image_url":
                    parts.append(
                        {"inline_data": {"mime_type": "image/jpeg", "data": item["image_url"]["url"].split(',')[1]}})
        else:
            parts.append({"text": message_content})
        return parts

    def change_last_message_to_user_for_gemini(self, api_model, combined_messages):
        if combined_messages and ("gemini" in api_model.lower() or "gemma" in api_model.lower()) and \
                combined_messages[-1]["role"] in {"system","model","assistant"}:
            logger.info(f"Adjusting last message for {api_model}: system -> user with [SYSTEM INFO] prefix.")
            combined_messages[-1]["role"] = "user"
            combined_messages[-1]["content"] = f"[SYSTEM INFO] {combined_messages[-1]['content']}"

    def clear_endline_sim(self, params):
        for key, value in params.items():
            if isinstance(value, str):
                params[key] = value.replace("'\x00", "").replace("\x00", "")