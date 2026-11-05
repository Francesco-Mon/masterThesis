"""A fake OpenRouter for offline tests: httpx.MockTransport answering chat completions.

`FakeOpenRouter(["{...}", ...])` replies with the given contents in order (the last one
repeats); a reply may also be an int (HTTP error status). Every request body is kept in
`requests`, so tests can inspect the messages and the response_format sent.
"""

import json

import httpx


class FakeOpenRouter:
    def __init__(self, replies, cost=0.001, prompt_tokens=100, completion_tokens=20):
        self.replies = list(replies)
        self.cost, self.prompt_tokens, self.completion_tokens = (
            cost,
            prompt_tokens,
            completion_tokens,
        )
        self.requests: list[dict] = []
        self.headers: list[httpx.Headers] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(request.headers)
        i = min(len(self.requests), len(self.replies)) - 1
        reply = self.replies[i]
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": {"message": "fake", "code": reply}})
        return httpx.Response(
            200,
            json={
                "id": f"gen-{len(self.requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "provider": "FakeProvider",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": reply},
                    }
                ],
                "usage": {
                    "prompt_tokens": self.prompt_tokens,
                    "completion_tokens": self.completion_tokens,
                    "total_tokens": self.prompt_tokens + self.completion_tokens,
                    "cost": self.cost,
                },
            },
        )

    def http_client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))
