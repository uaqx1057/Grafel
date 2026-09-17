import json
import os
import re
import subprocess
import sys

from grafel_core.proof import append_graph_use_event
from grafel_core.savings import count_tokens


# Quote-aware: src="a path with spaces.py" OR bare src=path (no spaces).
# The bare branch stops at whitespace or "]" (attributes live in [...] blocks).
SRC_RE = re.compile(r"\bsrc=(?:\"([^\"]+)\"|([^]\s]+))")

# How many recent successful query/path/explain results keep their files in
# the read allowlist. Accumulating forever would let one broad early query
# unlock files for the whole server lifetime; resetting on every graph call
# would break legitimate drill-down flows (query, then path/explain, then
# read files from either result). A small sliding window keeps multi-step
# flows working while old grants age out.
ALLOWLIST_RESULT_WINDOW = 5


def normalize_repo_path(repo_path):
    return os.path.normcase(os.path.normpath(os.path.realpath(repo_path)))


def path_within_repo(repo_path, candidate):
    repo = normalize_repo_path(repo_path)
    path = os.path.normcase(os.path.normpath(os.path.realpath(candidate)))
    return path == repo or path.startswith(repo + os.sep)


def resolve_repo_file(repo_path, user_path):
    candidate = user_path
    if not os.path.isabs(candidate):
        candidate = os.path.join(repo_path, candidate)
    candidate = os.path.normpath(candidate)
    if not path_within_repo(repo_path, candidate):
        raise PermissionError("file is outside the Grafel-controlled repo")
    return candidate


def source_files_from_graph_output(repo_path, text):
    files = set()
    for match in SRC_RE.finditer(text or ""):
        rel = (match.group(1) or match.group(2) or "").strip().strip('"').strip("'")
        if not rel or rel.startswith("<"):
            continue
        try:
            resolved = resolve_repo_file(repo_path, rel)
        except PermissionError:
            continue
        if os.path.isfile(resolved):
            files.add(os.path.normcase(os.path.realpath(resolved)))
    return files


def run_graphify(repo_path, graphify_cmd, command, args):
    proc = subprocess.run(
        list(graphify_cmd) + [command] + list(args or []),
        cwd=repo_path,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return proc.returncode, proc.stdout or ""


class StrictGateway:
    def __init__(self, repo_path, graphify_cmd):
        self.repo_path = os.path.abspath(repo_path)
        self.graphify_cmd = graphify_cmd
        # Sliding window of per-result file sets; allowed_files is their union.
        self._recent_result_files = []
        self.allowed_files = set()
        self.query_seen = False

    def _grant_result_files(self, files):
        if not files:
            # A result with no src= files neither grants nor revokes access.
            return
        self._recent_result_files.append(set(files))
        self._recent_result_files = self._recent_result_files[-ALLOWLIST_RESULT_WINDOW:]
        self.allowed_files = set().union(*self._recent_result_files)

    def graph_command(self, command, args, source="strict_mcp"):
        code, out = run_graphify(self.repo_path, self.graphify_cmd, command, args)
        tokens, _ = count_tokens(out) if out.strip() else (0, False)
        success = code == 0 and bool(out.strip())
        if command in ("query", "path", "explain") and success:
            self.query_seen = True
            self._grant_result_files(source_files_from_graph_output(self.repo_path, out))
        if success:
            append_graph_use_event(
                self.repo_path,
                source=source,
                command=command,
                argv=list(args or []),
                cwd=self.repo_path,
                tokens=tokens,
                success=True,
                session_hint="strict_mcp",
            )
        return {"code": code, "output": out, "tokens": tokens}

    def allowed_files_list(self):
        repo = normalize_repo_path(self.repo_path)
        out = []
        for fp in sorted(self.allowed_files):
            try:
                rel = os.path.relpath(fp, repo)
            except ValueError:
                rel = fp
            out.append(rel)
        return out

    def read_file(self, path, max_chars=20000):
        resolved = resolve_repo_file(self.repo_path, path)
        key = os.path.normcase(os.path.realpath(resolved))
        if not self.query_seen:
            raise PermissionError("run grafel.query first; strict gateway blocks raw repo reads")
        if key not in self.allowed_files:
            raise PermissionError(
                "file was not returned by a recent Grafel graph query/path/explain "
                f"result (last {ALLOWLIST_RESULT_WINDOW} results)"
            )
        with open(resolved, encoding="utf-8", errors="replace") as f:
            return f.read(max(1, int(max_chars or 20000)))

    def search_allowed(self, pattern, max_matches=50):
        if not self.query_seen:
            raise PermissionError("run grafel.query first; strict gateway blocks raw repo search")
        rx = re.compile(pattern, re.IGNORECASE)
        matches = []
        for fp in sorted(self.allowed_files):
            try:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, 1):
                        if rx.search(line):
                            rel = os.path.relpath(fp, self.repo_path)
                            matches.append(f"{rel}:{lineno}: {line.strip()[:220]}")
                            if len(matches) >= int(max_matches or 50):
                                return "\n".join(matches)
            except OSError:
                continue
        return "\n".join(matches) if matches else "(no matches in graph-allowed files)"

    def file_summary(self, path, max_chars=12000):
        text = self.read_file(path, max_chars=max_chars)
        lines = text.splitlines()
        nonempty = [line.strip() for line in lines if line.strip()]
        preview = "\n".join(nonempty[:40])
        return (
            f"File: {path}\n"
            f"Lines sampled: {len(lines)}\n"
            f"Characters sampled: {len(text)}\n\n"
            f"{preview}"
        )


def tool_schemas():
    return [
        {
            "name": "grafel.query",
            "description": "Mandatory first step for codebase questions. Queries Grafel's graph and grants read access to returned files.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "budget": {"type": "integer", "default": 2000},
                },
                "required": ["question"],
            },
        },
        {
            "name": "grafel.path",
            "description": "Find graph path/relationship between two symbols or files and grant read access to returned files.",
            "inputSchema": {
                "type": "object",
                "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
                "required": ["from", "to"],
            },
        },
        {
            "name": "grafel.explain",
            "description": "Explain a focused concept from the graph and grant read access to returned files.",
            "inputSchema": {
                "type": "object",
                "properties": {"concept": {"type": "string"}},
                "required": ["concept"],
            },
        },
        {
            "name": "grafel.read_file",
            "description": "Read a repo file only after Grafel graph results have allowed it.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 20000},
                },
                "required": ["path"],
            },
        },
        {
            "name": "grafel.allowed_files",
            "description": "List files currently allowed by recent Grafel graph query/path/explain results.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "grafel.search_allowed",
            "description": "Search only files allowed by Grafel graph results.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "max_matches": {"type": "integer", "default": 50},
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "grafel.file_summary",
            "description": "Summarize one graph-allowed file without broad repo reads.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 12000},
                },
                "required": ["path"],
            },
        },
        {
            "name": "grafel.save_result",
            "description": "Save/reuse a high-quality graph-backed answer for this repo.",
            "inputSchema": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    ]


def content_result(text):
    return {"content": [{"type": "text", "text": text or ""}]}


def error_response(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def success_response(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def handle_tool_call(gateway, name, args):
    args = args or {}
    if name == "grafel.query":
        question = args.get("question") or ""
        budget = str(args.get("budget") or 2000)
        result = gateway.graph_command("query", [question, "--budget", budget])
        return content_result(result["output"])
    if name == "grafel.path":
        result = gateway.graph_command("path", [args.get("from") or "", args.get("to") or ""])
        return content_result(result["output"])
    if name == "grafel.explain":
        result = gateway.graph_command("explain", [args.get("concept") or ""])
        return content_result(result["output"])
    if name == "grafel.save_result":
        result = gateway.graph_command("save-result", [args.get("question") or ""])
        return content_result(result["output"])
    if name == "grafel.read_file":
        return content_result(gateway.read_file(args.get("path") or "", args.get("max_chars") or 20000))
    if name == "grafel.allowed_files":
        return content_result("\n".join(gateway.allowed_files_list()) or "(no files allowed yet)")
    if name == "grafel.search_allowed":
        return content_result(gateway.search_allowed(args.get("pattern") or "", args.get("max_matches") or 50))
    if name == "grafel.file_summary":
        return content_result(gateway.file_summary(args.get("path") or "", args.get("max_chars") or 12000))
    raise ValueError(f"unknown tool: {name}")


def serve_stdio(repo_path, graphify_cmd):
    gateway = StrictGateway(repo_path, graphify_cmd)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            method = req.get("method")
            request_id = req.get("id")
            if method == "initialize":
                resp = success_response(request_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "grafel-strict", "version": "1.0.0"},
                })
            elif method == "tools/list":
                resp = success_response(request_id, {"tools": tool_schemas()})
            elif method == "tools/call":
                params = req.get("params") or {}
                resp = success_response(
                    request_id,
                    handle_tool_call(gateway, params.get("name"), params.get("arguments") or {}),
                )
            elif method == "notifications/initialized":
                continue
            else:
                resp = error_response(request_id, -32601, f"unknown method: {method}")
        except Exception as exc:
            request_id = None
            try:
                request_id = json.loads(line).get("id")
            except Exception:
                pass
            resp = error_response(request_id, -32000, str(exc))
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
