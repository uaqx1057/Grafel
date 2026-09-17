import tempfile
from pathlib import Path


class TempRepoHarness:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".git").mkdir()

    def close(self):
        self._tmp.cleanup()

    def write_code(self, name="demo.py", text="def hello():\n    return 1\n"):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_workspace(self, repo_name="repo", workspace_name="demo.code-workspace"):
        repo = self.root / repo_name
        repo.mkdir(exist_ok=True)
        ws = self.root / workspace_name
        ws.write_text('{"folders":[{"path":"' + repo_name + '"}]}', encoding="utf-8")
        return ws, repo


class FakeProcess:
    def __init__(self, returncode=0):
        self.returncode = returncode

    def poll(self):
        return self.returncode
