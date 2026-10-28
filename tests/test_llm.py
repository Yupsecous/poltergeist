import os
import socket
import unittest
from unittest import mock

from poltergeist.llm import Client, NotLocalError, ServerError, assert_loopback

from .fakeserver import FakeLlama


class LoopbackTest(unittest.TestCase):
    def test_accepts_addresses_on_this_machine(self):
        for url in ("http://127.0.0.1:8081", "http://localhost:8081", "http://[::1]:8081", "http://127.1.2.3/v1"):
            assert_loopback(url)

    def test_refuses_everything_else(self):
        for url in (
            "http://192.168.1.20:8081",
            "http://0.0.0.0:8081",
            "https://api.example.com",
            "http://localhost.evil.example",
            "http://127.0.0.1.evil.example",
            "not a url",
        ):
            with self.subTest(url=url), self.assertRaises(NotLocalError):
                assert_loopback(url)

    def test_the_client_refuses_to_be_built_for_a_remote_host(self):
        with self.assertRaises(NotLocalError):
            Client("http://10.0.0.5:8081")


class ClientTest(unittest.TestCase):
    def test_sends_a_deterministic_schema_constrained_request(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        with FakeLlama({"a": "b"}) as server:
            reply = Client(server.url).chat("sys", "usr", schema=schema, seed=3, max_tokens=50)
        (body,) = server.requests
        self.assertEqual(0, body["temperature"])
        self.assertEqual(3, body["seed"])
        self.assertEqual(50, body["max_tokens"])
        self.assertEqual(schema, body["response_format"]["json_schema"]["schema"])
        self.assertEqual([{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}], body["messages"])
        self.assertEqual('{"a": "b"}', reply.text)
        self.assertEqual((11, 7), (reply.prompt_tokens, reply.completion_tokens))

    def test_ignores_proxy_settings(self):
        with FakeLlama({"a": "b"}) as server, mock.patch.dict(
            os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9", "NO_PROXY": ""}
        ):
            self.assertEqual('{"a": "b"}', Client(server.url).chat("s", "u").text)

    def test_model_name_comes_from_the_server(self):
        with FakeLlama({}) as server:
            self.assertEqual("fake-model", Client(server.url).model_name())

    def test_reports_a_server_that_is_not_there(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with self.assertRaises(ServerError):
            Client(f"http://127.0.0.1:{port}", timeout=2).chat("s", "u")


if __name__ == "__main__":
    unittest.main()
