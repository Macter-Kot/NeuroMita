from .base import BaseProvider, LLMRequest
from main_logger import logger

class G4FProvider(BaseProvider):
    name = "g4f"
    priority = 40

    def is_applicable(self, req: LLMRequest) -> bool:
        return req.g4f_flag

    def generate(self, req: LLMRequest) -> str:
        return self._generate_g4f_response(req)

    def _generate_g4f_response(self, req: LLMRequest) -> str:
        if req.depth > 3:
            logger.error("Слишком много рекурсивных tool-вызовов (g4f).")
            return None

        try:
            from g4f.client import Client as g4fClient
            target_client = g4fClient()
            model_to_use = req.g4f_model or "gpt-3.5-turbo"
            logger.info(f"Using g4f client with model: {model_to_use}")
        except ImportError:
            logger.error("g4f not available")
            return None

        try:
            self.change_last_message_to_user_for_gemini(model_to_use, req.messages)

            cleaned_messages = []
            for msg in req.messages:
                cleaned_msg = {k: v for k, v in msg.items() if k != "time"}
                cleaned_messages.append(cleaned_msg)

            final_params = self.get_final_params(model_to_use, cleaned_messages, req)

            if req.tools_on and req.tools_mode == "native" and req.tools_payload:
                final_params["tools"] = req.tools_payload
                final_params["stream"] = False

            logger.info(
                f"Requesting completion from {model_to_use} with temp={final_params.get('temperature')}, max_tokens={final_params.get('max_tokens')}, stream={req.stream}")
            completion = target_client.chat.completions.create(**final_params, stream=req.stream)

            if req.stream:
                return self._handle_openai_stream(completion, req.stream_cb)
            elif completion and completion.choices:
                import json
                message = completion.choices[0].message
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments)
                        from tools.manager import mk_tool_call_msg, mk_tool_resp_msg
                        tool_manager = req.extra.get('tool_manager')
                        if tool_manager:
                            tool_result = tool_manager.run(name, args)
                            req.messages.append(mk_tool_call_msg(name, args))
                            req.messages.append(mk_tool_resp_msg(name, tool_result))
                            req.depth += 1
                            return self._generate_g4f_response(req)

                response_content = completion.choices[0].message.content
                logger.info("Completion successful.")
                return response_content.strip() if response_content else None
            else:
                logger.warning("No completion choices received or completion object is empty.")
                if completion:
                    self.try_print_error(completion)
                return None
        except Exception as e:
            logger.error(f"Error during g4f API call: {str(e)}", exc_info=True)
            return None

    def _handle_openai_stream(self, completion, stream_callback: callable = None) -> str:
        full_response_parts = []
        try:
            for chunk in completion:
                response_content = ""
                try:
                    if chunk.choices and chunk.choices[0].delta:
                        response_content = chunk.choices[0].delta.content or ""
                    elif hasattr(chunk, 'candidates') and chunk.candidates and chunk.candidates[0].content and \
                            chunk.candidates[0].content.parts:
                        response_content = chunk.candidates[0].content.parts[0].text or ""
                except (AttributeError, IndexError) as e:
                    logger.debug(f"Could not extract content from stream chunk: {chunk}, error: {e}")
                    continue

                if response_content:
                    if stream_callback:
                        stream_callback(response_content)
                    full_response_parts.append(response_content)

            full_text = "".join(full_response_parts)
            logger.info("g4f stream finished.")
            return full_text
        except Exception as e:
            logger.error(f"Error processing g4f stream: {e}", exc_info=True)
            return "".join(full_response_parts)

    def change_last_message_to_user_for_gemini(self, api_model, combined_messages):
        if combined_messages and ("gemini" in api_model.lower() or "gemma" in api_model.lower()) and \
                combined_messages[-1]["role"] in {"system","model","assistant"}:
            logger.info(f"Adjusting last message for {api_model}: system -> user with [SYSTEM INFO] prefix.")
            combined_messages[-1]["role"] = "user"
            combined_messages[-1]["content"] = f"[SYSTEM INFO] {combined_messages[-1]['content']}"

    def get_final_params(self, model, messages, req):
        final_params = {
            "model": model,
            "messages": messages,
        }
        final_params.update(req.extra)
        self.clear_endline_sim(final_params)
        return final_params

    def clear_endline_sim(self, params):
        for key, value in params.items():
            if isinstance(value, str):
                params[key] = value.replace("'\x00", "").replace("\x00", "")

    def try_print_error(self, completion_or_error):
        logger.warning("Attempting to print error details from API response/error object.")
        if not completion_or_error:
            logger.warning("No error object or completion data to parse.")
            return

        if hasattr(completion_or_error, 'error') and completion_or_error.error:
            error_data = completion_or_error.error
            logger.warning(
                f"API Error: Code={getattr(error_data, 'code', 'N/A')}, Message='{getattr(error_data, 'message', 'N/A')}', Type='{getattr(error_data, 'type', 'N/A')}'")
            if hasattr(error_data, 'param') and error_data.param:
                logger.warning(f"  Param: {error_data.param}")
        elif isinstance(completion_or_error, dict) and 'error' in completion_or_error:
            error_data = completion_or_error['error']
            logger.warning(f"API Error (from dict): {error_data}")
        elif hasattr(completion_or_error, 'message'):
            logger.warning(f"API Error: {completion_or_error.message}")
        else:
            logger.warning(f"Could not parse detailed error. Raw object: {str(completion_or_error)[:500]}")