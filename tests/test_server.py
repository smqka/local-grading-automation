import unittest

from grading_api.config import Settings
from grading_api.server import create_server


def settings_without_api_key() -> Settings:
    return Settings(
        host="127.0.0.1",
        port=0,
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="fake-model",
        prompt_version="test-prompt",
        request_timeout_seconds=1,
        max_image_bytes=1024,
        api_token=None,
        allowed_origins=("http://localhost:5173",),
    )


class ServerStartupTest(unittest.TestCase):
    def test_server_can_start_without_openai_key_for_health_checks(self):
        server = create_server(settings_without_api_key())
        try:
            self.assertIsNotNone(server.server_address)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
