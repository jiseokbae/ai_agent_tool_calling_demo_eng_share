# streamlit_app.py

import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import streamlit as st

import config
from call_context import CallContext
from phone_assistant_agent import PhoneAssistantAgent, formatting_call_from_messages

LOCAL_TZ = ZoneInfo(config.LOCAL_TIMEZONE)

st.set_page_config(
    page_title="전화 대신 받기 API 연동 테스트",
    layout="wide",
)


def make_json_safe(obj: Any):
    """
    Streamlit json / 저장용 안전 변환.
    혹시 pydantic 객체나 tool_call 객체가 섞여도 최대한 dict/string으로 변환.
    """
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, list):
        return [make_json_safe(x) for x in obj]

    if isinstance(obj, tuple):
        return [make_json_safe(x) for x in obj]

    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}

    if hasattr(obj, "model_dump"):
        return make_json_safe(obj.model_dump())

    if hasattr(obj, "__dict__"):
        return make_json_safe(obj.__dict__)

    return str(obj)


def get_agent_trace_messages(agent: PhoneAssistantAgent) -> list[dict[str, Any]]:
    return getattr(agent, "trace_messages", getattr(agent, "messages", []))


def get_agent_dialogue_messages(agent: PhoneAssistantAgent) -> list[dict[str, Any]]:
    return getattr(agent, "dialogue_messages", getattr(agent, "messages", []))

def get_agent_llm_input_logs(agent: PhoneAssistantAgent) -> list[dict[str, Any]]:
    return getattr(agent, "llm_input_logs", [])

def create_agent() -> PhoneAssistantAgent:
    call_context = CallContext(
        spam_level=st.session_state.spam_level,
        is_open=st.session_state.is_open == "Yes",
        user_name=st.session_state.user_name,
        status=st.session_state.user_status,
        call_time=st.session_state.call_time,
    )

    agent = PhoneAssistantAgent()
    agent.set_user(call_context=call_context, ai_history=None)
    return agent


def build_reference_now_from_ui() -> tuple[str | None, str | None]:
    """
    사용자가 입력한 날짜/시간 문자열을 한국시간 ISO 문자열로 변환한다.

    입력 형식:
    - 날짜: 24/10/06
    - 시간: 13:00

    반환:
    - 성공: ("2024-10-06T13:00:00+09:00", None)
    - 실패: (None, "에러 메시지")
    """

    date_text = st.session_state.reference_date_text.strip()
    time_text = st.session_state.reference_time_text.strip()

    if not date_text or not time_text:
        return None, "날짜와 시간을 모두 입력해야 합니다. 예: 24/10/06, 13:00"

    try:
        dt = datetime.strptime(
            f"{date_text} {time_text}",
            "%y/%m/%d %H:%M",
        )
    except ValueError:
        return None, "입력 형식이 잘못됐습니다. 날짜는 24/10/06, 시간은 13:00 형식으로 입력하세요."

    dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.isoformat(), None


def reset_call() -> bool:
    reference_now, error = build_reference_now_from_ui()

    if error:
        st.error(error)
        return False

    config.REFERENCE_NOW = reference_now

    st.session_state.agent = create_agent()
    st.session_state.turn_logs = []
    st.session_state.call_ended = False

    opening = st.session_state.agent.get_opening_message()

    st.session_state.turn_logs.append(
        {
            "speaker": "assistant",
            "text": opening,
            "actions": [],
            "end_call": False,
        }
    )

    return True


def flatten_tool_results(turn_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_results: list[dict[str, Any]] = []

    for turn in turn_logs:
        actions = turn.get("actions") or []
        for action in actions:
            tool_results.append(action)

    return tool_results


def build_output() -> dict[str, Any]:
    agent: PhoneAssistantAgent = st.session_state.agent

    trace_messages = get_agent_trace_messages(agent)
    dialogue_messages = get_agent_dialogue_messages(agent)
    llm_input_logs = get_agent_llm_input_logs(agent)
    
    output = {
        "meta": {
            "spam_level": st.session_state.spam_level,
            "is_open": st.session_state.is_open,
            "user_name": st.session_state.user_name,
            "user_status": st.session_state.user_status,
            "call_time": st.session_state.call_time,
            "reference_now": config.REFERENCE_NOW,
            "saved_at": datetime.now(LOCAL_TZ).isoformat(),
        },
        "turn_logs": st.session_state.turn_logs,
        "tool_results": flatten_tool_results(st.session_state.turn_logs),

        # 저장/디버그용 전체 로그
        "trace_messages": trace_messages,

        # LLM 입력용 실제 대화 로그
        "dialogue_messages": dialogue_messages,

        # 실제 매 LLM 호출에 들어간 messages
        "llm_input_logs": llm_input_logs,

        # 실제 RX/TX 대화
        "conversation": formatting_call_from_messages(dialogue_messages),
    }

    return make_json_safe(output)


def ensure_state():
    now_local = datetime.now(LOCAL_TZ)

    defaults = {
        "spam_level": "safe",
        "is_open": "Yes",
        "user_name": "Jack",
        "user_status": "driving",
        "call_time": "5 PM",

        # 기준 시간 입력값
        "reference_date_text": now_local.strftime("%y/%m/%d"),
        "reference_time_text": now_local.strftime("%H:%M"),

        "turn_logs": [],
        "call_ended": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "agent" not in st.session_state:
        reset_call()


ensure_state()

st.title("전화 대신 받기 API 연동 테스트")

# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------
with st.sidebar:
    st.header("통화 메타정보")

    st.selectbox(
        "spam_level",
        ["safe", "dangerous"],
        key="spam_level",
    )

    st.selectbox(
        "공개 설정",
        ["Yes", "No"],
        key="is_open",
    )

    st.text_input(
        "사용자 이름",
        key="user_name",
    )

    st.text_input(
        "사용자 상태",
        key="user_status",
    )

    st.text_input(
        "콜백 가능 시간",
        key="call_time",
        help="상대방이 언제 다시 연락하면 되는지 물을 때만 안내할 참고 시간입니다.",
    )

    st.divider()

    st.subheader("기준 날짜/시간")

    st.text_input(
        "날짜",
        key="reference_date_text",
        placeholder="24/10/06",
        help="YY/MM/DD 형식으로 입력하세요. 예: 24/10/06",
    )

    st.text_input(
        "시간",
        key="reference_time_text",
        placeholder="13:00",
        help="24시간제 HH:MM 형식으로 입력하세요. 예: 13:00",
    )

    reference_now, error = build_reference_now_from_ui()

    if error:
        st.caption(f"입력 오류: {error}")
    else:
        st.caption(f"기준 시간: {reference_now} ({config.LOCAL_TIMEZONE})")

    st.divider()

    if st.button("새 통화 시작", use_container_width=True):
        if reset_call():
            st.rerun()

    output = build_output()
    st.download_button(
        label="결과 JSON 다운로드",
        data=json.dumps(output, ensure_ascii=False, indent=2),
        file_name="interactive_result.json",
        mime="application/json",
        use_container_width=True,
    )


agent: PhoneAssistantAgent = st.session_state.agent


# ------------------------------------------------------------
# 대화 출력
# ------------------------------------------------------------
for turn in st.session_state.turn_logs:
    speaker = turn.get("speaker")
    text = turn.get("text", "")

    if speaker == "caller":
        with st.chat_message("user"):
            st.write(text)

    elif speaker == "assistant":
        with st.chat_message("assistant"):
            st.write(text)

            actions = turn.get("actions") or []
            if actions:
                with st.expander("Tool calls / results"):
                    st.json(make_json_safe(actions))


if st.session_state.call_ended:
    st.warning("통화가 종료되었습니다. 새 통화를 시작하려면 왼쪽의 [새 통화 시작]을 누르세요.")


# ------------------------------------------------------------
# 사용자 입력
# ------------------------------------------------------------
caller_text = st.chat_input(
    "상대방 발화를 입력하세요",
    disabled=st.session_state.call_ended,
)

if caller_text:
    st.session_state.turn_logs.append(
        {
            "speaker": "caller",
            "text": caller_text,
        }
    )

    result = agent.get_response(caller_text)

    reply_text = result["reply_text"]
    actions = result["actions"]
    end_call = result["end_call"]

    st.session_state.turn_logs.append(
        {
            "speaker": "assistant",
            "text": reply_text,
            "actions": actions,
            "end_call": end_call,
        }
    )

    if end_call:
        st.session_state.call_ended = True

    st.rerun()


# ------------------------------------------------------------
# 디버그 패널
# ------------------------------------------------------------
st.divider()

trace_messages = get_agent_trace_messages(agent)
dialogue_messages = get_agent_dialogue_messages(agent)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Conversation",
        "Tool Results",
        "Dialogue Messages",
        "LLM Input Logs",
        "Trace Messages",
        "Download JSON Preview",
    ]
)

with tab1:
    st.text(formatting_call_from_messages(dialogue_messages))

with tab2:
    st.json(make_json_safe(flatten_tool_results(st.session_state.turn_logs)))

with tab3:
    st.caption("LLM에 계속 넣는 실제 대화 history입니다. 과거 tool_call/tool_result는 제외됩니다.")
    st.json(make_json_safe(dialogue_messages))

with tab4:
    st.caption(
        "실제로 매 LLM chat 호출에 들어간 messages입니다. "
        "dialogue_messages에 현재 round의 tool_call/compact tool_result가 임시로 붙은 형태입니다."
    )

    llm_input_logs = get_agent_llm_input_logs(agent)

    if not llm_input_logs:
        st.info("아직 LLM 호출 로그가 없습니다.")
    else:
        selected_idx = st.selectbox(
            "LLM 호출 선택",
            options=list(range(len(llm_input_logs))),
            format_func=lambda i: (
                f"#{llm_input_logs[i].get('call_index')} "
                f"/ round {llm_input_logs[i].get('tool_round')} "
                f"/ messages {llm_input_logs[i].get('message_count')} "
                f"/ input: {llm_input_logs[i].get('caller_input')}"
            ),
        )

        selected_log = llm_input_logs[selected_idx]

        st.subheader("Selected LLM Input")
        st.json(make_json_safe(selected_log))

        st.subheader("Messages Only")
        st.json(make_json_safe(selected_log.get("messages", [])))

with tab5:
    st.caption("저장/디버그용 전체 로그입니다. tool_call/tool_result 전체가 포함됩니다.")
    st.json(make_json_safe(trace_messages))

with tab6:
    st.json(build_output())