# interactive_main.py

import argparse
import json
from typing import Any

from call_context import CallContext
from phone_assistant_agent import PhoneAssistantAgent, formatting_call_from_messages


def make_call_context_from_args(args) -> CallContext:
    return CallContext(
        spam_level=args.spam_level,
        is_open=args.is_open == "Yes",
        user_name=args.name,
        status=args.status,
        call_time=args.call_time,
    )


def get_agent_trace_messages(assistant: PhoneAssistantAgent) -> list[dict[str, Any]]:
    return getattr(assistant, "trace_messages", getattr(assistant, "messages", []))


def get_agent_dialogue_messages(assistant: PhoneAssistantAgent) -> list[dict[str, Any]]:
    return getattr(assistant, "dialogue_messages", getattr(assistant, "messages", []))


def print_actions(actions: list[dict[str, Any]]):
    if not actions:
        return

    print("\n[ACTIONS]")
    for action in actions:
        print(f"- tool: {action.get('tool')}")
        print(f"  tool_call_id: {action.get('tool_call_id')}")
        print(f"  raw_arguments: {action.get('raw_arguments')}")
        print(f"  args: {json.dumps(action.get('args'), ensure_ascii=False, indent=2)}")
        print(f"  result: {json.dumps(action.get('result'), ensure_ascii=False, indent=2)}")

import os
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import config

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--spam_level", type=str, default="safe", choices=["safe", "dangerous"])
    parser.add_argument("--is_open", type=str, default="Yes", choices=["Yes", "No"])
    parser.add_argument("--name", type=str, default="Jack")
    parser.add_argument("--status", type=str, default="driving")
    parser.add_argument("--call_time", type=str, default="5 PM")

    parser.add_argument("--scenario_id", type=str, default="manual")
    parser.add_argument("--save_path", type=str, default=None)

    args = parser.parse_args()

    if args.save_path is None:
        timestamp = datetime.now(
            ZoneInfo(config.LOCAL_TIMEZONE)
        ).strftime("%Y%m%d_%H%M%S")

        args.save_path = (
            f"./results/{args.scenario_id}_{timestamp}.json"
        )

    os.makedirs(
        os.path.dirname(os.path.abspath(args.save_path)),
        exist_ok=True,
    )


    call_context = make_call_context_from_args(args)

    assistant = PhoneAssistantAgent()
    assistant.set_user(call_context=call_context, ai_history=None)

    print("🔔 --- 전화 대신 받기 API 연동 테스트 ---")
    print("명령어:")
    print("  /quit      종료")
    print("  /history   실제 RX/TX 대화")
    print("  /dialogue  LLM 입력용 dialogue_messages")
    print("  /trace       저장/디버그용 trace_messages")
    print("  /save      저장")
    print("-" * 70)

    opening = assistant.get_opening_message()
    print(f"\n🤖 [AI비서]: {opening}")

    turn_logs: list[dict[str, Any]] = [
        {
            "speaker": "assistant",
            "text": opening,
            "actions": [],
            "end_call": False,
        }
    ]

    while True:
        caller_text = input("\n👤 [상대/사용자 입력]: ").strip()

        if not caller_text:
            continue

        if caller_text == "/quit":
            break

        if caller_text == "/history":
            print("\n[CONVERSATION]")
            print(
                formatting_call_from_messages(
                    get_agent_dialogue_messages(assistant)
                )
            )
            continue

        if caller_text == "/dialogue":
            print("\n[DIALOGUE_MESSAGES]")
            print(
                json.dumps(
                    get_agent_dialogue_messages(assistant),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue

        if caller_text == "/trace":
            print("\n[TRACE_MESSAGES]")
            print(
                json.dumps(
                    get_agent_trace_messages(assistant),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            continue

        if caller_text == "/save":
            save_result(
                path=args.save_path,
                assistant=assistant,
                turn_logs=turn_logs,
                args=args,
                call_context=call_context,
            )
            print(f"[SAVE] {args.save_path}")
            continue

        turn_logs.append(
            {
                "speaker": "caller",
                "text": caller_text,
            }
        )

        result = assistant.get_response(caller_text)

        reply_text = result["reply_text"]
        actions = result["actions"]
        end_call = result["end_call"]

        print_actions(actions)

        # 중요: end_call=True여도 마지막 멘트를 먼저 출력한다.
        print(f"\n🤖 [AI비서]: {reply_text}")

        turn_logs.append(
            {
                "speaker": "assistant",
                "text": reply_text,
                "actions": actions,
                "end_call": end_call,
            }
        )

        if end_call:
            print("\n❌ --- AI가 마지막 멘트를 말한 뒤 통화를 종료했습니다. ---")
            break

    save_result(
        path=args.save_path,
        assistant=assistant,
        turn_logs=turn_logs,
        args=args,
        call_context=call_context,
    )
    print(f"\n[SAVE] {args.save_path}")


def flatten_tool_results(turn_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_results: list[dict[str, Any]] = []

    for turn in turn_logs:
        actions = turn.get("actions") or []
        for action in actions:
            tool_results.append(action)

    return tool_results

from copy import deepcopy
def save_result(
    path: str,
    assistant: PhoneAssistantAgent,
    turn_logs: list[dict[str, Any]],
    args,
    call_context: CallContext,
):

    trace_messages = deepcopy(get_agent_trace_messages(assistant))
    dialogue_messages = deepcopy(get_agent_dialogue_messages(assistant))

    output = {
        "metadata": {
            "scenario_id": args.scenario_id,
            "saved_at": datetime.now(
                ZoneInfo(config.LOCAL_TIMEZONE)
            ).isoformat(),
            "model_family": config.MODEL_FAMILY,
            "model_id": config.ASSISTANT_MODEL_ID,
            "timezone": config.LOCAL_TIMEZONE,
            "call_context": {
                "spam_level": call_context.spam_level,
                "is_open": call_context.is_open,
                "user_name": call_context.user_name,
                "status": call_context.status,
                "call_time": call_context.call_time,
            },
        },
        "turn_logs": turn_logs,
        "tool_results": flatten_tool_results(turn_logs),

        # 저장/디버그용 전체 로그
        "trace_messages": trace_messages,

        # LLM 입력용 실제 대화 로그
        "dialogue_messages": dialogue_messages,

        # 사람이 보는 RX/TX 대화
        "conversation": formatting_call_from_messages(dialogue_messages),
    }

    try:
        summary = assistant.get_summary()
        output["summary"] = summary
    except Exception as e:
        output["summary_error"] = {
            "type": type(e).__name__,
            "message": str(e),
        }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()