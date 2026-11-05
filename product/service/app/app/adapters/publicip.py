"""이 컴퓨터의 공인 IP 보기.

화면에서 단추를 누를 때만 공개 서비스 한 곳(api.ipify.org)에 GET을 한 번 보낸다(실제 전송이 켜진 때만 · transport.py). 저절로 부르지 않는다.
토스 · 증권사 주소가 아니다. 결과는 저장하지 않고 그대로 돌려준다.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Callable

IP_URL = "https://api.ipify.org?format=json"
TIMEOUT_S = 10.0

# 주소를 받아 응답 본문(bytes)을 돌려준다. 시험은 가짜를 넣는다.
IpFetch = Callable[[str], bytes]


class PublicIpError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def public_ip(fetch: IpFetch) -> str:
    try:
        raw = fetch(IP_URL)
    except (TimeoutError, OSError, ValueError):
        raise PublicIpError("공인 IP를 받지 못했어요 · 인터넷 연결을 확인하고 다시 눌러 주세요") from None
    try:
        text = str(json.loads(raw.decode("utf-8"))["ip"])
        return str(ipaddress.ip_address(text.strip()))
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise PublicIpError("공인 IP를 읽지 못했어요 · 잠시 뒤 다시 눌러 주세요") from None
