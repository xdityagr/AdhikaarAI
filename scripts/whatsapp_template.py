"""
Create and check the WhatsApp message templates A3 needs.

    python scripts/whatsapp_template.py --list
    python scripts/whatsapp_template.py --create scheme_update --lang en
    python scripts/whatsapp_template.py --create scheme_update --lang hi

Meta allows free-form messages only inside a 24-hour window that opens when the
PERSON messages us. A template is the only thing that can open that window from
our side.

WHY THIS TEMPLATE SAYS SO LITTLE

It is deliberately generic and carries no variables at all:

  - **No scheme name.** One template then serves every alert, instead of one
    per scheme waiting in Meta's review queue.
  - **No amount of money, ever.** A figure in a push message that turns out to
    be wrong is the one mistake this product cannot make. The template says
    there is an update; the person taps, the window opens, and the engine
    computes the real figure inside the conversation where it can be explained.
  - **No name.** A variable Meta requires us to fill, that we often do not have,
    is a template that cannot be sent. Static text always sends.

The quick-reply buttons matter more than they look. Tapping one sends a message
back, which is what opens the window — and for somebody who reads slowly or
types with difficulty, a tap is the difference between replying and not.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings                      # noqa: E402

GRAPH = "https://graph.facebook.com"

#: Every template we define, by name then language. Adding a language is adding
#: an entry here, not editing one — Meta treats each language as its own
#: template with its own review.
TEMPLATES: dict[str, dict[str, dict]] = {
    "scheme_update": {
        "en": {
            "body": (
                "You asked Yojna Setu to tell you when a government scheme you "
                "may qualify for changes, or when a new one opens.\n\n"
                "There is an update waiting for you. Tap below and we will "
                "tell you what it is, in your language."
            ),
            "footer": "You can stop these messages at any time.",
            "buttons": ["See my update", "Stop these messages"],
        },
        "hi": {
            "body": (
                "आपने योजना सेतु से कहा था कि जिन सरकारी योजनाओं के आप हक़दार हो "
                "सकते हैं, उनमें कोई बदलाव हो या कोई नई योजना आए तो आपको बताएँ।\n\n"
                "आपके लिए एक अपडेट है। नीचे टैप कीजिए, हम आपकी भाषा में बताएँगे "
                "कि वह क्या है।"
            ),
            "footer": "आप कभी भी ये संदेश बंद करा सकते हैं।",
            "buttons": ["अपडेट देखें", "संदेश बंद करें"],
        },
    },
}


def _components(spec: dict) -> list[dict]:
    components: list[dict] = [{"type": "BODY", "text": spec["body"]}]
    if spec.get("footer"):
        components.append({"type": "FOOTER", "text": spec["footer"]})
    if spec.get("buttons"):
        components.append({
            "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": text}
                        for text in spec["buttons"]],
        })
    return components


def _api() -> tuple[str, str, str]:
    settings = get_settings()
    waba = settings.whatsapp_business_account_id
    token = settings.whatsapp_token
    version = settings.whatsapp_api_version or "v21.0"
    if not waba:
        raise SystemExit("WHATSAPP_BUSINESS_ACCOUNT_ID is not set")
    if not token:
        raise SystemExit("No WhatsApp token (WHATSAPP_SAT or WHATSAPP_ACCESS_TOKEN)")
    return waba, token, version


def show(_args) -> int:
    waba, token, version = _api()
    response = httpx.get(f"{GRAPH}/{version}/{waba}/message_templates",
                         params={"limit": 100},
                         headers={"Authorization": f"Bearer {token}"},
                         timeout=30)
    if response.status_code != 200:
        print(response.text[:800])
        return 1
    for template in response.json().get("data", []):
        print(f"  {template.get('name'):34} {template.get('language'):7} "
              f"{template.get('category'):10} {template.get('status')}")
        if template.get("status") == "REJECTED":
            print(f"      reason: {template.get('rejected_reason')}")
    return 0


def create(args) -> int:
    spec = TEMPLATES.get(args.create, {}).get(args.lang)
    if spec is None:
        raise SystemExit(
            f"No definition for {args.create}/{args.lang}. "
            f"Known: {json.dumps({k: list(v) for k, v in TEMPLATES.items()})}")

    waba, token, version = _api()
    payload = {
        "name": args.create,
        "language": args.lang,
        # UTILITY because this follows from something the person did — they
        # asked to be told. Meta reclassifies liberally and may return
        # MARKETING; take it rather than rewording this into something
        # misleading, since the opt-in MARKETING needs is already in place.
        "category": args.category,
        "components": _components(spec),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("\n  dry run — nothing submitted")
        return 0

    response = httpx.post(f"{GRAPH}/{version}/{waba}/message_templates",
                          json=payload,
                          headers={"Authorization": f"Bearer {token}"},
                          timeout=30)
    print(f"\n  -> {response.status_code} {response.text[:600]}")
    return 0 if response.status_code < 400 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="show every template")
    parser.add_argument("--create", help="template name to submit")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--category", default="UTILITY",
                        choices=["UTILITY", "MARKETING"])
    parser.add_argument("--dry-run", action="store_true",
                        help="print the payload, submit nothing")
    args = parser.parse_args()
    if args.create:
        return create(args)
    return show(args)


if __name__ == "__main__":
    raise SystemExit(main())
