import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grading_api.config import load_settings


class ConfigTest(unittest.TestCase):
    def test_load_settings_reads_dotenv_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=from-dotenv",
                        "GRADING_API_PORT=9876",
                        "GRADING_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(env_path=env_path)

        self.assertEqual(settings.openai_api_key, "from-dotenv")
        self.assertEqual(settings.port, 9876)
        self.assertEqual(
            settings.allowed_origins,
            ("http://localhost:5173", "http://127.0.0.1:5173"),
        )

    def test_dotenv_does_not_override_existing_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("OPENAI_API_KEY=from-dotenv", encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "from-env"}, clear=True):
                settings = load_settings(env_path=env_path)

        self.assertEqual(settings.openai_api_key, "from-env")

    def test_dotenv_overrides_empty_environment_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("OPENAI_API_KEY=from-dotenv", encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True):
                settings = load_settings(env_path=env_path)

        self.assertEqual(settings.openai_api_key, "from-dotenv")

    def test_litterbox_image_url_mode_sets_upload_defaults(self):
        with patch.dict(os.environ, {"GRADING_IMAGE_URL_MODE": "litterbox"}, clear=True):
            settings = load_settings(env_path=Path("missing.env"))

        self.assertEqual(settings.image_upload_url, "https://litterbox.catbox.moe/resources/internals/api.php")
        self.assertEqual(settings.image_upload_field, "fileToUpload")
        self.assertEqual(settings.image_upload_response_format, "text")
        self.assertEqual(settings.image_upload_extra_fields, (("reqtype", "fileupload"), ("time", "1h")))

    def test_imgbb_image_url_mode_sets_upload_defaults(self):
        with patch.dict(
            os.environ,
            {
                "GRADING_IMAGE_URL_MODE": "imgbb",
                "IMGBB_API_KEY": "test-key",
                "IMGBB_EXPIRATION_SECONDS": "300",
            },
            clear=True,
        ):
            settings = load_settings(env_path=Path("missing.env"))

        self.assertEqual(settings.image_upload_url, "https://api.imgbb.com/1/upload?expiration=300&key=test-key")
        self.assertEqual(settings.image_upload_field, "image")
        self.assertEqual(settings.image_upload_response_format, "json")
        self.assertEqual(settings.image_upload_response_path, "data.medium.url")


if __name__ == "__main__":
    unittest.main()
