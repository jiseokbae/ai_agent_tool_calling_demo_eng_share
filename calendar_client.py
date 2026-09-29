# calendar_client.py

from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]



def get_calendar_service():
    creds = None

    token_path = config.GOOGLE_TOKEN_PATH
    credentials_path = config.GOOGLE_CREDENTIALS_PATH

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    except Exception:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path,
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        with open(token_path, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build(
        "calendar",
        "v3",
        credentials=creds,
        cache_discovery=False,
    )


def check_google_calendar(
    start_datetime: str,
    end_datetime: str,
    calendar_id: str | None = None,
) -> dict[str, Any]:
    target_calendar_id = calendar_id or config.GOOGLE_CALENDAR_ID

    try:
        service = get_calendar_service()

        body = {
            "timeMin": start_datetime,
            "timeMax": end_datetime,
            "items": [
                {
                    "id": target_calendar_id,
                }
            ],
        }

        response = service.freebusy().query(body=body).execute()

        calendar_info = response.get("calendars", {}).get(target_calendar_id, {})
        errors = calendar_info.get("errors", [])

        # if errors:
        #     return {
        #         "ok": False,
        #         "status": "calendar_error",
        #         "available": None,
        #         "calendar_id": target_calendar_id,
        #         "busy_blocks": [],
        #         "errors": errors,
        #         "message_for_assistant": (
        #             "캘린더 조회 중 오류가 발생했습니다. "
        #             "상대방에게는 확인 후 전달하겠다고 말하세요."
        #         ),
        #     }

        if errors:
            return {
                "ok": False,
                "status": "calendar_error",
                "available": None,
                "calendar_id": target_calendar_id,
                "busy_blocks": [],
                "errors": errors,
            }
        
        busy_list = calendar_info.get("busy", [])

        busy_blocks = [
            {
                "start": busy.get("start"),
                "end": busy.get("end"),
                "visibility": "busy",
                "detail_policy": "do_not_disclose_event_title",
            }
            for busy in busy_list
        ]

        # if busy_blocks:
        #     return {
        #         "ok": True,
        #         "status": "busy",
        #         "available": False,
        #         "calendar_id": target_calendar_id,
        #         "busy_blocks": busy_blocks,
        #         "message_for_assistant": (
        #             "요청한 시간대에는 일정이 있습니다. "
        #             "상세 일정명은 말하지 말고, 해당 시간은 어려울 수 있다고 안내하세요."
        #         ),
        #     }

        if busy_blocks:
            return {
                "ok": True,
                "status": "busy",
                "available": False,
                "calendar_id": target_calendar_id,
                "busy_blocks": busy_blocks,
            }

        # return {
        #     "ok": True,
        #     "status": "available",
        #     "available": True,
        #     "calendar_id": target_calendar_id,
        #     "busy_blocks": [],
        #     "message_for_assistant": (
        #         "요청한 시간대에는 일정이 없습니다. "
        #         "다만 사용자 승인 없이 약속을 확정하지 말고 가능할 수 있다고만 말하세요."
        #     ),
        # }

        return {
            "ok": True,
            "status": "available",
            "available": True,
            "calendar_id": target_calendar_id,
            "busy_blocks": [],
        }

    # except Exception as e:
    #     return {
    #         "ok": False,
    #         "status": "error",
    #         "available": None,
    #         "calendar_id": target_calendar_id,
    #         "busy_blocks": [],
    #         "error_type": type(e).__name__,
    #         "error": str(e),
    #         "message_for_assistant": (
    #             "캘린더 조회 중 오류가 발생했습니다. "
    #             "상대방에게는 확인 후 전달하겠다고 말하세요."
    #         ),
    #     }

    
    except Exception as e:
        return {
            "ok": False,
            "status": "error",
            "available": None,
            "calendar_id": target_calendar_id,
            "busy_blocks": [],
            "error_type": type(e).__name__,
            "error": str(e),
        }