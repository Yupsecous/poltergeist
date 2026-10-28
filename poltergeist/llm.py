"""A client for a local llama.cpp server, and nothing else.

The client talks plain HTTP to an OpenAI-compatible endpoint and refuses any address that is not a loopback
address, so "it never leaves your machine" is enforced by code rather than promised by a README.
"""

from __future__ import annotations

import ipaddress
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class NotLocalError(RuntimeError):
    """The server address is not on this machine."""


class ServerError(RuntimeError):
    """The server could not be reached or answered with an error."""


@dataclass(frozen=True)
class Reply:
    text: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float


def assert_loopback(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise NotLocalError(f"{url} is not a loopback address; poltergeist only talks to a model on this machine")


class Client:
    def __init__(self, base_url: str = "http://127.0.0.1:8081", *, timeout: float = 900.0) -> None:
        assert_loopback(base_url)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # No proxies: a request for 127.0.0.1 must never be handed to anything else.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def chat(
        self,
        system: str,
        user: str,
        *,
        schema: dict | None = None,
        max_tokens: int = 400,
        seed: int = 7,
    ) -> Reply:
        body: dict = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "seed": seed,
            "max_tokens": max_tokens,
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "diagnosis", "strict": True, "schema": schema},
            }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ServerError(f"no usable answer from {self.base_url}: {error}") from error
        usage = payload.get("usage", {})
        return Reply(
            text=payload["choices"][0]["message"]["content"] or "",
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            seconds=time.monotonic() - started,
        )

    def model_name(self) -> str:
        try:
            with self._opener.open(f"{self.base_url}/v1/models", timeout=10) as response:
                return json.load(response)["data"][0]["id"]
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError):
            return "unknown"
