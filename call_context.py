# call_context.py

from dataclasses import dataclass
from typing import Literal

from assistant_prompt import CALL_USER_NOTOPEN_PROMPT, CALL_USER_OPEN_PROMPT


SpamLevel = Literal["safe", "dangerous"]


@dataclass
class CallContext:
    spam_level: SpamLevel
    is_open: bool

    # Name of the user receiving the call, not the caller.
    user_name: str | None = None

    status: str | None = None
    call_time: str | None = None


def build_opening_message(context: CallContext) -> str:
    """
    Fixed opening message used at the beginning of each call.
    """
    return (
        "Hi, they can't take the call right now, so I'm their AI assistant. "
        "Please let me know what you're calling about, and I'll make sure it gets passed along."
    )


def build_user_context_prompt(context: CallContext) -> str:
    """
    Build the user/call metadata prompt provided to the LLM.

    Information may be disclosed only when:
    - is_open=True
    - spam_level="안전"

    Internal spam values remain Korean for compatibility with the existing UI,
    but the value passed to the LLM is converted to English.
    """

    can_open = context.is_open and context.spam_level == "safe"

    if can_open:
        return CALL_USER_OPEN_PROMPT.format(
            spam_level=context.spam_level,
            user_name=context.user_name or "not provided",
            user_status=context.status or "not provided",
            user_call_time=context.call_time or "None",
        )

    return CALL_USER_NOTOPEN_PROMPT.format(
        spam_level=context.spam_level,
    )