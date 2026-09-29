# llm_client.py

from typing import Any

from openai import OpenAI

class ChatLLMClient:
    def __init__(self, base_url: str, model_name: str, api_key: str = "EMPTY"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        extra_body: dict[str, Any] | None = None,
    ):
        kwargs = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools is not None:
            kwargs["tools"] = tools

        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

        if extra_body is not None:
            kwargs["extra_body"] = extra_body

        return self.client.chat.completions.create(**kwargs)