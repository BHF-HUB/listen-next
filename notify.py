"""Optional push notifications through ntfy.sh (free; just an app + a topic name)."""
import os

from . import http


def send(title, message, click_url=None):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return False
    headers = {"Title": title.encode("utf-8"), "Tags": "headphones"}
    if click_url:
        headers["Click"] = click_url
    try:
        r = http.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                      headers=headers, host_key="ntfy")
        return r.status_code < 300
    except Exception:
        return False
