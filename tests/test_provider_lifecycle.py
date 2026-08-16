import json
import os
import unittest
from unittest.mock import patch

from core.model_router.credentials import CredentialStore
from core.model_router.models import RouteRequest
from core.model_router.providers.openai_provider import OpenAIProvider
from core.model_router.providers.openrouter_provider import OpenRouterProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConfig:
    def __init__(self, keys=None):
        self.keys = keys or {}

    def get_api_key(self, provider):
        return self.keys.get(provider)


class ProviderLifecycleTests(unittest.TestCase):
    def test_environment_credentials_take_precedence(self):
        store = CredentialStore(FakeConfig({"openai": "file-key"}))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}, clear=False):
            self.assertEqual(store.get("openai"), "env-key")

    def test_persistent_credentials_are_resolved(self):
        store = CredentialStore(FakeConfig({"openai": "file-key"}))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(store.get("openai"), "file-key")

    def test_openai_completion_uses_chat_contract(self):
        provider = OpenAIProvider(api_key="test-key")
        response = FakeResponse({"choices": [{"message": {"content": "hello"}}]})
        with patch("core.model_router.providers.cloud_provider.urlopen", return_value=response) as mocked:
            result = provider.complete(RouteRequest(prompt="hi", model="gpt-4o"))
        self.assertEqual(result, "hello")
        request = mocked.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "gpt-4o")
        self.assertEqual(body["messages"][-1]["content"], "hi")
        self.assertNotIn("test-key", request.data.decode("utf-8"))

    def test_openrouter_inherits_openai_compatible_transport(self):
        provider = OpenRouterProvider(api_key="test-key")
        response = FakeResponse({"choices": [{"message": {"content": "fallback"}}]})
        with patch("core.model_router.providers.cloud_provider.urlopen", return_value=response):
            result = provider.complete(RouteRequest(prompt="hello", model="qwen/qwen3-coder:free"))
        self.assertEqual(result, "fallback")

    def test_missing_credentials_do_not_make_cloud_provider_healthy(self):
        self.assertFalse(OpenAIProvider().check_health())


if __name__ == "__main__":
    unittest.main()
