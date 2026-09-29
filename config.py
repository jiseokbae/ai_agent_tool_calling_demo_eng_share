LOCAL_TIMEZONE = "America/Los_Angeles"
LOCAL_CITY = "Los Angeles"
LOCAL_REGION = "CA"
LOCAL_COUNTRY = "US"


# 전화 대신 받는 AI 비서 모델
ASSISTANT_LLM_API_URL = "http://localhost:8888/v1"


MODEL_FAMILY = "gemma4"  # "gemma4" 또는 "exaone"

if MODEL_FAMILY == "gemma4":
    # ASSISTANT_MODEL_ID = "gemma-4-12B-it"
    ASSISTANT_MODEL_ID = "gemma-4-26B-A4B-it-FP8-dynamic"
    
    LLM_EXTRA_BODY = None

API_KEY = "EMPTY"

MAX_TURNS = 10

MOCK_INCLUDE_FAILURES = False
# ------------------------------------------------------------
# Google Calendar API
# ------------------------------------------------------------
GOOGLE_CREDENTIALS_PATH = "/home/jiseokbae/projects/ai_agent_tool_calling/calendar_api/credentials.json"
GOOGLE_TOKEN_PATH = "/home/jiseokbae/projects/ai_agent_tool_calling/calendar_api/token.json"
GOOGLE_CALENDAR_ID = "primary"


# ------------------------------------------------------------
# Google Places API
# ------------------------------------------------------------
GOOGLE_PLACES_API_KEY =  ""

# Los Angeles 기준 위치
GOOGLE_PLACES_LATITUDE = 34.0522
GOOGLE_PLACES_LONGITUDE = -118.2437
GOOGLE_PLACES_RADIUS_METERS = 40000.0

# ------------------------------------------------------------
# 테스트 기준 시간
# None이면 실제 현재 시간 사용
# 문자열이면 해당 시간을 기준으로 날짜/시간 정규화
# 예: "2026-05-20T19:55:00+09:00"
# ------------------------------------------------------------
REFERENCE_NOW = None

# ------------------------------------------------------------



# SUMMARY_SYSTEM_PROMPT = """
# 너는 전화 통화 내용을 요약하는 비서다.

# 입력은 RX/TX 형식의 통화 로그다.
# - RX: 발신자 발화
# - TX: AI비서 발화

# 출력은 아래 형식으로 간결하게 작성한다.

# 요약:
# - 발신자 목적:
# - 주요 내용:
# - 사용자가 해야 할 일:
# - 통화 종료 이유:
# """


SUMMARY_SYSTEM_PROMPT = """
You are an assistant that summarizes phone calls.

The input is a phone call log in RX/TX format.
- RX: caller's utterance
- TX: AI assistant's utterance

Write a concise summary in the following format:

Summary:
- Caller's purpose:
- Key details:
- Action required from the user:
- Reason the call ended:
"""