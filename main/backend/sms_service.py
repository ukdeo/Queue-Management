import datetime
import http.client
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

INFOBIP_BASE_URL = os.getenv("INFOBIP_BASE_URL", "")
API_KEY = os.getenv("INFOBIP_API_KEY", "")
SENDER = os.getenv("INFOBIP_SENDER", "PALO")
SIMULATION_MODE = os.getenv("SMS_SIMULATION_MODE", "false").lower() == "true"


def send_sms(phone_number: str, message: str) -> bool:
    if not phone_number:
        return False

    clean_phone = ''.join(filter(str.isdigit, phone_number))
    
    # Auto-prepend Nepal country code (977) if number is 10 digits starting with 9
    if len(clean_phone) == 10 and clean_phone.startswith('9'):
        clean_phone = "977" + clean_phone

    if SIMULATION_MODE:
        border = "*" * 60
        print(f"\n{border}")
        print(f"[SMS SIMULATION MODE ACTIVE]")
        print(f"[TO]: {clean_phone}")
        print(f"[MSG]: {message}")
        print(f"{border}\n")
        return True

    if not API_KEY or not INFOBIP_BASE_URL:
        print("[SMS] WARNING: INFOBIP_API_KEY or INFOBIP_BASE_URL not set in .env — SMS skipped.")
        return False

    try:
        conn = http.client.HTTPSConnection(INFOBIP_BASE_URL)

        payload = json.dumps({
            "messages": [
                {
                    "from": SENDER,
                    "destinations": [
                        {"to": clean_phone}
                    ],
                    "text": message
                }
            ]
        })

        headers = {
            "Authorization": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        conn.request("POST", "/sms/2/text/advanced", payload, headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")

        border = "=" * 50
        print(f"\n{border}")
        print(f"[INFOBIP SMS SENT TO]: {clean_phone}")
        print(f"[TIME]: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[MESSAGE]: {message}")
        print(f"[STATUS]: {res.status}")
        print(f"[RESPONSE]: {data}")
        print(f"{border}\n")

        return res.status in (200, 201, 202)

    except Exception as e:
        print(f"[ERROR] Failed to send SMS: {e}")
        return False