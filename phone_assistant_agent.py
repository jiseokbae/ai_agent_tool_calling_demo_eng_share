# phone_assistant_agent.py

import copy
import json
import re
from typing import Any

import config
from assistant_prompt import CALL_SYSTEM_PROMPT
from call_context import CallContext, build_opening_message, build_user_context_prompt
from config import (
    API_KEY,
    ASSISTANT_LLM_API_URL,
    ASSISTANT_MODEL_ID,
    SUMMARY_SYSTEM_PROMPT,
)
from llm_client import ChatLLMClient
from tools import TOOLS, dumps_tool_result, execute_tool


class PhoneAssistantAgent:
    def __init__(self):
        self.llm = ChatLLMClient(
            base_url=ASSISTANT_LLM_API_URL,
            model_name=ASSISTANT_MODEL_ID,
            api_key=API_KEY,
        )

        # LLM에 계속 넣는 실제 대화 history
        # system / call_context / 실제 RX / 실제 TX만 유지
        self.dialogue_messages: list[dict[str, Any]] = []

        # 저장/디버그용 전체 로그 
        # tool_call / full tool_result / raw API result까지 전부 보관
        self.trace_messages: list[dict[str, Any]] = []

        # 실제 매 LLM chat 호출에 들어간 messages snapshot
        # dialogue_messages + 현재 tool round의 compact tool_result
        self.llm_input_logs: list[dict[str, Any]] = []
        self.last_llm_messages: list[dict[str, Any]] = []

        # 기존 코드 호환용
        # 외부에서 assistant.messages를 참조하면 trace_messages를 보게 둔다.
        self.messages: list[dict[str, Any]] = self.trace_messages

        self.opening_message: str = ""

    def set_user(
        self,
        call_context: CallContext,
        ai_history: list[dict[str, Any]] | None = None,
    ):
        """
        새 통화 시작 또는 기존 history 복원.

        dialogue_messages:
        - LLM에 계속 넣을 실제 대화 history
        - 과거 tool_call/tool_result 제외

        trace_messages:
        - 저장/디버그용 전체 로그
        - full tool result 보관

        llm_input_logs:
        - 매 LLM 호출에 실제로 들어간 messages snapshot
        """

        self.opening_message = build_opening_message(call_context)
        user_context_prompt = build_user_context_prompt(call_context)

        self.llm_input_logs = []
        self.last_llm_messages = []

        base_messages = [
            {
                "role": "system",
                "content": CALL_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_context_prompt,
            },
            {
                "role": "assistant",
                "content": self.opening_message,
            },
        ]

        if ai_history:
            self.trace_messages = list(ai_history)
            self.dialogue_messages = self._filter_dialogue_messages(ai_history)

            has_system = any(
                msg.get("role") == "system"
                for msg in self.dialogue_messages
            )
            has_call_context = any(
                msg.get("role") == "user"
                and "<call_context>" in (msg.get("content") or "")
                for msg in self.dialogue_messages
            )

            prefix: list[dict[str, Any]] = []

            if not has_system:
                prefix.append(
                    {
                        "role": "system",
                        "content": CALL_SYSTEM_PROMPT,
                    }
                )

            if not has_call_context:
                prefix.append(
                    {
                        "role": "user",
                        "content": user_context_prompt,
                    }
                )

            if prefix:
                self.dialogue_messages = prefix + self.dialogue_messages
                self.trace_messages = prefix + self.trace_messages

            self.messages = self.trace_messages
            return

        self.dialogue_messages = list(base_messages)
        self.trace_messages = list(base_messages)
        self.messages = self.trace_messages

    def get_opening_message(self) -> str:
        return self.opening_message

    def get_response(self, caller_input: str) -> dict[str, Any]:
        """
        발신자 발화 1턴을 받아서 AI비서 응답을 반환한다.

        LLM 입력:
        - 기존 실제 대화 history
        - 현재 tool round에서 막 발생한 tool_call/tool_result만 임시 포함

        저장:
        - trace_messages에는 전체 tool_call/tool_result 보존
        - llm_input_logs에는 실제 LLM 입력 snapshot 보존
        """

        user_msg = {
            "role": "user",
            "content": caller_input,
        }

        self.dialogue_messages.append(user_msg)
        self.trace_messages.append(user_msg)

        actions: list[dict[str, Any]] = []
        max_tool_rounds = 4

        # 현재 caller_input 1턴 안에서만 유지되는 tool context.
        # 다음 사용자 턴으로 넘어가면 과거 tool 결과는 LLM 입력에서 빠진다.
        pending_tool_messages: list[dict[str, Any]] = []

        for tool_round in range(max_tool_rounds):
            llm_messages = self._build_llm_messages(
                pending_tool_messages=pending_tool_messages,
            )

            self._record_llm_input(
                caller_input=caller_input,
                tool_round=tool_round + 1,
                llm_messages=llm_messages,
            )

            response = self.llm.chat(
                messages=llm_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=2048,
                extra_body=getattr(config, "LLM_EXTRA_BODY", None),
            )

            assistant_msg = response.choices[0].message
            tool_calls = getattr(assistant_msg, "tool_calls", None)

            self._print_llm_debug(
                response=response,
                assistant_msg=assistant_msg,
                tool_calls=tool_calls,
            )

            # tool call이 없으면 일반 답변
            if not tool_calls:
                reply_text = assistant_msg.content or ""
                reply_text = self._sanitize_reply(reply_text)

                if not reply_text.strip():
                    print("\n[EMPTY_CONTENT_WARNING]")
                    print("finish_reason =", response.choices[0].finish_reason)

                    reasoning = getattr(assistant_msg, "reasoning", None)
                    if reasoning:
                        print("reasoning_len =", len(reasoning))

                    reply_text = "Sorry, could you say that one more time?"

                assistant_text_msg = {
                    "role": "assistant",
                    "content": reply_text,
                }

                self.dialogue_messages.append(assistant_text_msg)
                self.trace_messages.append(assistant_text_msg)

                return {
                    "reply_text": reply_text,
                    "end_call": False,
                    "actions": actions,
                }

            # trace 저장용 tool_call 메시지
            trace_tool_call_msg = self._assistant_tool_call_to_dict(
                assistant_msg,
                include_debug=True,
            )
            self.trace_messages.append(trace_tool_call_msg)

            # LLM 입력용 tool_call 메시지
            # content/debug 제거된 순수 tool_call만 현재 round에 임시 포함
            llm_tool_call_msg = self._assistant_tool_call_to_dict(
                assistant_msg,
                include_debug=False,
            )
            pending_tool_messages.append(llm_tool_call_msg)

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                raw_arguments = tool_call.function.arguments

                print("\n[RAW_TOOL_CALL]")
                print(f"name={tool_name}")
                print(f"arguments={raw_arguments}")

                try:
                    args = self._parse_tool_args(raw_arguments)
                    tool_result = execute_tool(tool_name, args)

                except Exception as e:
                    args = {}
                    tool_result = {
                        "ok": False,
                        "tool": tool_name,
                        "error_type": type(e).__name__,
                        "error": str(e),
                        "message_for_assistant": (
                            "An error occurred while running the tool. "
                            "Tell the caller that the information will be noted and passed along."
                        ),
                    }

                    if tool_name == "end_call":
                        tool_result.update(
                            {
                                "should_end_call": True,
                                "reason_type": "other",
                                "reason": "Invalid end_call tool arguments",
                                "closing_message": "Thank you. I'll pass along what you've told me.",
                            }
                        )

                action = {
                    "tool_call_id": tool_call.id,
                    "tool": tool_name,
                    "raw_arguments": raw_arguments,
                    "args": args,
                    "result": tool_result,
                }
                actions.append(action)

                # raw 저장용: full tool result
                raw_tool_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": dumps_tool_result(tool_result),
                }
                self.trace_messages.append(raw_tool_msg)

                # LLM 입력용: compact tool result
                llm_tool_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": self._dumps_tool_result_for_llm(tool_result),
                }
                pending_tool_messages.append(llm_tool_msg)

                # end_call은 실제 hangup이 아니라 마지막 멘트 후 종료 신호
                if tool_name == "end_call" or tool_result.get("should_end_call") is True:
                    reply_text = tool_result.get(
                        "closing_message",
                        "Thank you. I'll pass along what you've told me.",
                    )
                    reply_text = self._sanitize_reply(reply_text)

                    assistant_text_msg = {
                        "role": "assistant",
                        "content": reply_text,
                    }

                    self.dialogue_messages.append(assistant_text_msg)
                    self.trace_messages.append(assistant_text_msg)

                    return {
                        "reply_text": reply_text,
                        "end_call": True,
                        "actions": actions,
                    }

            # 현재 turn의 tool_call/tool_result만 pending_tool_messages에 남긴 채 다음 LLM 호출
            # 예: resolve_place -> notify_user -> end_call 연쇄 가능

        # tool loop가 너무 길어지는 경우 fallback
        reply_text = "Thank you. I'll pass along what you've told me."
        reply_text = self._sanitize_reply(reply_text)

        assistant_text_msg = {
            "role": "assistant",
            "content": reply_text,
        }

        self.dialogue_messages.append(assistant_text_msg)
        self.trace_messages.append(assistant_text_msg)

        return {
            "reply_text": reply_text,
            "end_call": True,
            "actions": actions,
        }

    def _build_llm_messages(
        self,
        pending_tool_messages: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        LLM에 넣을 메시지 구성.

        포함:
        - system prompt
        - call_context
        - 실제 RX/TX 대화 history
        - 현재 tool round의 tool_call/tool_result

        제외:
        - 과거 tool_call
        - 과거 tool_result
        - raw debug content
        """

        messages = list(self.dialogue_messages)

        if pending_tool_messages:
            messages.extend(pending_tool_messages)

        return messages

    def _record_llm_input(
        self,
        caller_input: str,
        tool_round: int,
        llm_messages: list[dict[str, Any]],
    ):
        """
        실제 LLM chat 호출에 들어간 messages snapshot을 저장한다.

        이 로그는 디버깅용이다.
        즉, '이번 LLM 호출에 지도 결과가 compact하게 들어갔는지',
        '과거 tool 결과가 빠졌는지' 확인하기 위한 용도다.
        """

        snapshot = copy.deepcopy(llm_messages)

        log = {
            "call_index": len(self.llm_input_logs) + 1,
            "caller_input": caller_input,
            "tool_round": tool_round,
            "message_count": len(snapshot),
            "messages": snapshot,
        }

        self.last_llm_messages = snapshot
        self.llm_input_logs.append(log)

    @staticmethod
    def _filter_dialogue_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        raw history에서 LLM 입력용 실제 대화만 추출한다.
        """

        dialogue: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")

            if role == "tool":
                continue

            if role == "assistant" and msg.get("tool_calls"):
                continue

            if role not in {"system", "user", "assistant"}:
                continue

            content = msg.get("content")
            if content is None:
                continue

            dialogue.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return dialogue

    @staticmethod
    def _sanitize_reply(reply: str) -> str:
        reply = (reply or "").strip()

        # content에 thinking이 직접 섞여 들어온 경우 제거
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        reply = reply.replace("</think>", "").strip()

        # 모델이 tool call이 아니라 텍스트로 tool syntax를 뱉는 경우 방어
        if "call." in reply or "tool_call" in reply or "<tool" in reply:
            return "Thank you. I'll pass along what you've told me."

        return reply

    def get_summary(self) -> str:
        call_text = formatting_call_from_messages(self.dialogue_messages)

        messages = [
            {
                "role": "system",
                "content": SUMMARY_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": call_text,
            },
        ]

        response = self.llm.chat(
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
            extra_body=getattr(config, "LLM_EXTRA_BODY", None),
        )

        return (response.choices[0].message.content or "").strip()

    @staticmethod
    def _assistant_tool_call_to_dict(
        assistant_msg,
        include_debug: bool = False,
    ) -> dict[str, Any]:
        """
        tool_call을 포함한 assistant 메시지는 실제 상대방에게 말한 TX가 아니다.
        EXAONE 등은 tool_call 메시지 content에 자연어/분석을 같이 넣을 수 있으므로,
        LLM 입력용 메시지에는 content와 debug 필드를 넣지 않는다.
        """

        original_content = assistant_msg.content or ""

        result = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in assistant_msg.tool_calls
            ],
        }

        if include_debug and original_content.strip():
            result["tool_call_content_debug"] = original_content

        return result

    @staticmethod
    def _parse_tool_args(raw_arguments: str) -> dict[str, Any]:
        try:
            args = json.loads(raw_arguments)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid tool arguments JSON: {raw_arguments}") from e

        if not isinstance(args, dict):
            raise ValueError(f"Tool arguments must be a JSON object: {raw_arguments}")

        return args

    @staticmethod
    def _compact_place_candidate(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
        if not candidate:
            return None

        return {
            "rank": candidate.get("rank"),
            "name": candidate.get("name"),
            "address": candidate.get("address"),
        }

    def _dumps_tool_result_for_llm(self, tool_result: dict[str, Any]) -> str:
        """
        LLM prompt에 넣을 compact tool result.
        raw 저장용 dumps_tool_result와 분리한다.

        여기서만 LLM에게 보여줄 tool 결과 필드를 조절한다.
        """

        tool = tool_result.get("tool")

        base: dict[str, Any] = {
            "ok": tool_result.get("ok"),
            "tool": tool,
            "status": tool_result.get("status"),
            "message_for_assistant": tool_result.get("message_for_assistant"),
        }

        if tool == "resolve_place":
            base.update(
                {
                    "query": tool_result.get("query"),
                    "resolved": tool_result.get("resolved"),
                    "selected_candidate": self._compact_place_candidate(
                        tool_result.get("selected_candidate")
                    ),
                    "top_candidates": [
                        self._compact_place_candidate(candidate)
                        for candidate in (tool_result.get("top_candidates") or [])[:3]
                    ],
                }
            )

        elif tool == "check_calendar_availability":
            normalized = tool_result.get("normalized_time") or {}

            compact_normalized = {
                "status": normalized.get("status"),
                "start_datetime": normalized.get("start_datetime"),
                "end_datetime": normalized.get("end_datetime"),
                "ask_user_message": normalized.get("ask_user_message"),
            }

            base.update(
                {
                    "requested_time_text": tool_result.get("requested_time_text"),
                    "duration_minutes": tool_result.get("duration_minutes"),
                    "available": tool_result.get("available"),
                    "missing_fields": tool_result.get("missing_fields"),
                    "normalized_time": compact_normalized,
                    "busy_count": len(tool_result.get("busy_blocks") or []),
                }
            )

        elif tool == "notify_user":
            base.update(
                {
                    "status": tool_result.get("status"),
                    "delivered": tool_result.get("delivered"),
                    "recorded": tool_result.get("recorded"),
                }
            )

        elif tool == "end_call":
            base.update(
                {
                    "should_end_call": tool_result.get("should_end_call"),
                    "reason_type": tool_result.get("reason_type"),
                    "closing_message": tool_result.get("closing_message"),
                }
            )

        else:
            for key in ["available", "resolved", "error_type", "error_code", "error"]:
                if key in tool_result:
                    base[key] = tool_result.get(key)

        return json.dumps(
            self._drop_empty(base),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _drop_empty(obj: Any) -> Any:
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                value = PhoneAssistantAgent._drop_empty(value)

                if value is None:
                    continue

                if value == []:
                    continue

                if value == {}:
                    continue

                cleaned[key] = value

            return cleaned

        if isinstance(obj, list):
            return [
                PhoneAssistantAgent._drop_empty(item)
                for item in obj
                if item is not None
            ]

        return obj

    @staticmethod
    def _print_llm_debug(response, assistant_msg, tool_calls):
        if getattr(config, "DEBUG_LLM", False):
            print("\n[RAW_LLM_RESPONSE]")
            try:
                print(response.model_dump_json(indent=2))
            except Exception:
                print(response)

            print("\n[ASSISTANT_MSG]")
            try:
                print(assistant_msg.model_dump_json(indent=2))
            except Exception:
                print(assistant_msg)

        print("\n[LLM_DEBUG]")
        print("finish_reason =", response.choices[0].finish_reason)
        print("content =", repr(assistant_msg.content))
        print("tool_calls =", bool(tool_calls))

        reasoning = getattr(assistant_msg, "reasoning", None)
        if reasoning:
            print("reasoning_len =", len(reasoning))


def formatting_call_from_messages(messages: list[dict[str, Any]]) -> str:
    call = ""

    for turn in messages:
        role = turn.get("role")
        content = turn.get("content") or ""

        if role == "system":
            continue

        if role == "tool":
            continue

        if role == "user" and "<call_context>" in content:
            continue

        if role == "user":
            if content:
                call += f"RX: {content}\n"

        elif role == "assistant":
            if turn.get("tool_calls"):
                continue

            if content:
                call += f"TX: {content}\n"

    return call.strip()