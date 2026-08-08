#!/usr/bin/env python3
"""
producer_studio_chat_client.py -- Producer as a literal Studio Chat client.

docs/planning/UNIFIED-BLUEPRINT-PIPELINE-PLAN.md section 4: Producer
drives real Studio Chat threads/messages through the same conversational
API and audit trail a human uses, tagged as an agent actor -- not a
privileged internal bypass. A human can open the exact thread Producer
built and keep working in it.

Real request flow, the same one a human client drives (three calls, no
shortcut endpoint invented for this):
  1. POST /api/v1/studio-chat/threads           (actor_type="agent")
  2. POST /api/v1/studio-chat/chat               (get the LLM's response)
  3. POST /api/v1/studio-chat/threads/{id}/build-jobs
                                                  (compile + submit)

Step 3 can come back `needs_clarification` (HTTP 422, Milestone 17's
compiler outcome). Per section 4: Producer answers it with its own
judgment and keeps going -- it appends one bounded "use your best
judgment, proceed with the most reasonable interpretation" follow-up and
retries once. It never blocks waiting for a human the way an attended
conversation would. This is intentionally the *same* clarification
mechanism a human sees in the UI, not a second one built for agents.

Reuses tools/studio_chat.py's post_json() rather than a second HTTP
helper.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from studio_chat import post_json  # noqa: E402

DEFAULT_MODEL = "oeb-qwen2.5-3b"
CLARIFICATION_AUTO_REPLY = (
    "Use your best judgment and proceed with the single most reasonable "
    "interpretation. Do not invent story content beyond what was given; "
    "prefer existing/registered assets, stand-ins, or simple primitives "
    "over anything elaborate."
)


class NeedsClarification(Exception):
    def __init__(self, detail: dict):
        self.detail = detail
        diagnostics = detail.get("diagnostics") or []
        reason = diagnostics[-1].get("reason") if diagnostics else None
        super().__init__(reason or "needs_clarification")


def create_agent_thread(harness_url: str, admin_token: str, title: str, actor_id: str = "producer") -> dict:
    return post_json(
        f"{harness_url.rstrip('/')}/api/v1/studio-chat/threads",
        {"title": title, "actor_type": "agent", "actor_id": actor_id},
        token=admin_token,
        timeout=30,
    )


def _ask_llm(harness_url: str, admin_token: str, thread_id: str, model: str, messages: list[dict]) -> str:
    response = post_json(
        f"{harness_url.rstrip('/')}/api/v1/studio-chat/chat",
        {"model": model, "thread_id": thread_id, "messages": messages, "stream": False},
        token=admin_token,
        timeout=480,
    )
    return response["message"]["content"]


def _submit_build_job(
    harness_url: str, admin_token: str, thread_id: str, creative_request: str,
    assistant_response: str, messages: list[dict],
) -> dict:
    try:
        return post_json(
            f"{harness_url.rstrip('/')}/api/v1/studio-chat/threads/{thread_id}/build-jobs",
            {
                "creative_request": creative_request,
                "assistant_response": assistant_response,
                "messages": messages,
            },
            token=admin_token,
            timeout=480,
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            detail = json.loads(exc.read().decode("utf-8")).get("detail") or {}
            if isinstance(detail, dict) and detail.get("outcome") == "needs_clarification":
                raise NeedsClarification(detail) from exc
        raise


def build_scene_via_studio_chat(
    harness_url: str,
    admin_token: str,
    creative_request: str,
    *,
    thread_title: str | None = None,
    model: str = DEFAULT_MODEL,
    actor_id: str = "producer",
) -> dict:
    """The real, end-to-end Producer-as-agent flow: create a thread,
    drive one round of chat, submit the build job, auto-answer at most
    one clarification round if the compiler asks for one, then return
    whatever the build-jobs endpoint returned (job/review_url/etc, or a
    final needs_clarification detail if even the auto-answered retry
    couldn't compile -- callers should ticket that case, not retry
    forever).
    """
    thread = create_agent_thread(harness_url, admin_token, thread_title or creative_request[:80], actor_id)
    thread_id = str(thread["id"])

    messages = [{"role": "user", "content": creative_request}]
    assistant_response = _ask_llm(harness_url, admin_token, thread_id, model, messages)

    try:
        result = _submit_build_job(
            harness_url, admin_token, thread_id, creative_request, assistant_response, messages,
        )
        return {"thread_id": thread_id, "clarified": False, **result}
    except NeedsClarification as clarification:
        messages.append({"role": "assistant", "content": assistant_response})
        messages.append({"role": "user", "content": CLARIFICATION_AUTO_REPLY})
        assistant_response = _ask_llm(harness_url, admin_token, thread_id, model, messages)
        try:
            result = _submit_build_job(
                harness_url, admin_token, thread_id, creative_request, assistant_response, messages,
            )
            return {"thread_id": thread_id, "clarified": True, **result}
        except NeedsClarification as second_clarification:
            # Never blocks: report the unresolved outcome for the caller
            # (Producer's own scene loop) to ticket and move on, per
            # section 4/6 -- this is not a retry-forever loop.
            return {
                "thread_id": thread_id,
                "clarified": False,
                "unresolved": True,
                "detail": second_clarification.detail,
            }


def parse_args():
    parser = argparse.ArgumentParser(prog="producer_studio_chat_client")
    parser.add_argument("--request", required=True, help="creative request / scene text")
    parser.add_argument("--harness-url", default=os.environ.get("OEB_HARNESS_URL"))
    parser.add_argument("--admin-token", default=os.environ.get("API_ADMIN_TOKEN"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--actor-id", default="producer")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.harness_url or not args.admin_token:
        print("[producer_studio_chat_client] ERROR: set OEB_HARNESS_URL and API_ADMIN_TOKEN", file=sys.stderr)
        return 2
    result = build_scene_via_studio_chat(
        args.harness_url, args.admin_token, args.request, model=args.model, actor_id=args.actor_id,
    )
    print(json.dumps(result, indent=2))
    return 0 if not result.get("unresolved") else 4


if __name__ == "__main__":
    sys.exit(main())
