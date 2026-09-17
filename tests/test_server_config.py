import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("grafel_server_app", ROOT / "server" / "app.py")
server_app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(server_app)


class ServerConfigTests(unittest.TestCase):
    def test_production_rejects_default_admin_token(self):
        with self.assertRaises(RuntimeError) as ctx:
            server_app.validate_runtime_config(
                env="production",
                admin_token="change-me-admin",
                latest={"url": "https://downloads.real.example/GrafelSetup.exe"},
                allow_insecure_defaults=False,
            )
        self.assertIn("default admin token", str(ctx.exception))

    def test_production_rejects_placeholder_update_url(self):
        with self.assertRaises(RuntimeError) as ctx:
            server_app.validate_runtime_config(
                env="production",
                admin_token="real-secret",
                latest={"url": "https://downloads.example.com/GrafelSetup.exe"},
                allow_insecure_defaults=False,
            )
        self.assertIn("placeholder download URL", str(ctx.exception))

    def test_development_allows_starter_defaults(self):
        server_app.validate_runtime_config(
            env="development",
            admin_token="change-me-admin",
            latest={"url": "https://downloads.example.com/GrafelSetup.exe"},
            allow_insecure_defaults=True,
        )


if __name__ == "__main__":
    unittest.main()
