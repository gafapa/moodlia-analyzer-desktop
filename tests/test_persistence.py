import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src import ai_settings, profiles


class PersistenceTests(unittest.TestCase):
    def test_profile_lifecycle_persists_updates_and_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_file = os.path.join(directory, "profiles.json")
            with patch.object(profiles, "PROFILES_DIR", directory), patch.object(
                profiles, "PROFILES_FILE", profile_file
            ):
                created = profiles.upsert_profile(
                    "Campus", "https://example.test", "token", "teacher"
                )
                self.assertEqual(created[0]["username"], "teacher")
                self.assertEqual(profiles.get_profile("Campus")["token"], "token")

                updated = profiles.upsert_profile(
                    "Campus", "https://updated.test", "new-token"
                )
                self.assertEqual(updated[0]["url"], "https://updated.test")
                self.assertNotIn("username", updated[0])

                self.assertEqual(profiles.delete_profile("Campus"), [])
                self.assertIsNone(profiles.get_profile("Campus"))

    def test_profile_loader_recovers_from_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_file = os.path.join(directory, "profiles.json")
            with open(profile_file, "w", encoding="utf-8") as handle:
                handle.write("{broken")
            with patch.object(profiles, "PROFILES_DIR", directory), patch.object(
                profiles, "PROFILES_FILE", profile_file
            ):
                self.assertEqual(profiles.load_profiles(), [])

    def test_ai_settings_merge_defaults_and_survive_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = os.path.join(directory, "ai_settings.json")
            with patch.object(ai_settings, "SETTINGS_DIR", directory), patch.object(
                ai_settings, "SETTINGS_FILE", settings_file
            ):
                self.assertEqual(ai_settings.load_ai_settings(), ai_settings.DEFAULT_SETTINGS)
                ai_settings.save_ai_settings({"provider": "lmstudio", "model": "local-model"})
                loaded = ai_settings.load_ai_settings()
                self.assertEqual(loaded["provider"], "lmstudio")
                self.assertEqual(loaded["model"], "local-model")
                self.assertEqual(loaded["base_url"], "http://127.0.0.1:11434")

                with open(settings_file, "r", encoding="utf-8") as handle:
                    self.assertEqual(json.load(handle), loaded)


if __name__ == "__main__":
    unittest.main()
