"""SSE 流式聊天端点测试（mock agent_run，离线运行）。

验证 /api/v1/chat/stream 的事件序列：start → delta*(真实 LLM 增量透传)
→ done(与非流式一致的完整信封)。
"""

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.agent import AgentResult
from app.api.chat import router
from app.models.message import Message, MessageRole


class _FakeTrace:
    """_build_chat_response 读取的 trace 字段（app_debug=True 时全部用到）。"""

    trace_id = "t-test"
    final_intent = "general"
    final_confidence = 0.9
    selected_flow = "GeneralFlow"
    selected_prompt = "general_prompt"
    total_duration_ms = 12.3
    reasoning = ""
    tool_calls: list = []
    session_id = "s-test"
    current_state = ""
    waiting_for = ""
    collected_slots: dict = {}


async def _fake_agent_run(**kwargs):
    # 模拟 call_llm 流式分支：从请求上下文取回调并逐段推送
    from app.services.llm import stream_callback

    cb = stream_callback.get()
    if cb is not None:
        cb("你")
        cb("好")
    return AgentResult(
        message=Message(role=MessageRole.ASSISTANT, content="你好"),
        intent_result=None,
        trace=_FakeTrace(),
    )


def _parse_sse(body: str) -> list[dict]:
    events = []
    for frame in body.split("\n\n"):
        for line in frame.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


class ChatStreamEndpointTest(unittest.TestCase):
    def setUp(self):
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        self.client = TestClient(test_app)

    def _post_stream(self, payload: dict) -> list[dict]:
        with patch("app.api.chat.agent_run", _fake_agent_run):
            with self.client.stream("POST", "/api/v1/chat/stream", json=payload) as resp:
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))
                body = "".join(resp.iter_text())
        return _parse_sse(body)

    def test_stream_emits_start_delta_done(self):
        events = self._post_stream({"message": "你好", "history": []})
        self.assertEqual(events[0]["type"], "start")
        deltas = [e for e in events if e["type"] == "delta"]
        self.assertEqual("".join(e["text"] for e in deltas), "你好")
        self.assertEqual(events[-1]["type"], "done")
        done_data = events[-1]["data"]["data"]
        self.assertTrue(events[-1]["data"]["success"])
        # done 携带清洗后的最终文本，与非流式端点一致
        self.assertEqual(done_data["reply"]["content"], "你好")

    def test_stream_forwards_session_id(self):
        captured = {}

        async def capturing_agent_run(**kwargs):
            captured.update(kwargs)
            return await _fake_agent_run(**kwargs)

        with patch("app.api.chat.agent_run", capturing_agent_run):
            with self.client.stream(
                "POST",
                "/api/v1/chat/stream",
                json={"message": "你好", "history": [{"role": "user", "content": "hi"}], "session_id": "s-1"},
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                "".join(resp.iter_text())
        self.assertEqual(captured["session_id"], "s-1")
        self.assertEqual(captured["user_message"], "你好")
        self.assertEqual(captured["history"], [{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
