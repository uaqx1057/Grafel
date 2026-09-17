import os
import re
import shutil
from datetime import datetime

from grafel_core.savings import count_tokens


BREVITY_START = "<!-- grafel-brevity:start -->"
BREVITY_END = "<!-- grafel-brevity:end -->"
BREVITY_LEVELS = {
    "lite": {
        "title": "Lite",
        "description": "Trim filler and hedging, keep full sentences.",
        "output_reduction": 0.25,
    },
    "full": {
        "title": "Full",
        "description": "Short engineer phrasing with fragments when clear.",
        "output_reduction": 0.45,
    },
    "ultra": {
        "title": "Ultra",
        "description": "Aggressive compression. Fragments first. Keep code exact.",
        "output_reduction": 0.60,
    },
}
BREVITY_DEFAULT = "full"
BREVITY_ALLOWED_EXT = {".md", ".txt", ".rst", ".typ", ".typst", ".tex", ""}
BREVITY_DENY_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml",
    ".env", ".lock", ".css", ".html", ".xml", ".sql", ".sh", ".ps1",
}

FILLER_PATTERNS = [
    (re.compile(r"\b(just|really|basically|actually|simply|essentially|generally)\b", re.I), ""),
    (re.compile(r"\b(sure|certainly|of course|happy to|i(?:'d| would) recommend)\b", re.I), ""),
    (re.compile(r"\b(it might be worth|you could consider|it would be good to)\b", re.I), ""),
    (re.compile(r"\b(in order to)\b", re.I), "to"),
    (re.compile(r"\b(make sure to)\b", re.I), ""),
    (re.compile(r"\b(the reason is because)\b", re.I), "because"),
    (re.compile(r"\b(however|furthermore|additionally|in addition)\b", re.I), ""),
]
ARTICLE_RE = re.compile(r"\b(a|an|the)\b", re.I)
SPACE_RE = re.compile(r"[ \t]{2,}")


def brevity_level_config(level):
    return BREVITY_LEVELS.get(level or "", BREVITY_LEVELS[BREVITY_DEFAULT])


def brevity_rule_block(level=BREVITY_DEFAULT):
    cfg = brevity_level_config(level)
    return (
        f"{BREVITY_START}\n"
        f"## Grafel Brevity Mode ({cfg['title']})\n"
        f"- Purpose: reduce output-token waste while preserving technical substance.\n"
        f"- Style: {cfg['description']}\n"
        "- Drop filler, pleasantries, and hedging.\n"
        "- Use short, direct engineering language. Fragments OK when clarity stays high.\n"
        "- Keep code, commands, paths, URLs, env vars, errors, versions, commit text, and irreversible warnings exact.\n"
        "- When user seems confused, safety risk high, or action irreversible: temporarily answer in normal clear prose.\n"
        "- Prefer pattern: [thing] [action] [reason]. [next step].\n"
        f"{BREVITY_END}\n"
    )


def write_brevity_block(path, level=BREVITY_DEFAULT, log=None):
    block = brevity_rule_block(level).strip()
    block_re = re.compile(
        re.escape(BREVITY_START) + r".*?" + re.escape(BREVITY_END), re.DOTALL
    )
    name = os.path.basename(path)
    try:
        existing = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                existing = f.read()
        if BREVITY_START in existing and BREVITY_END in existing:
            updated = block_re.sub(block, existing)
            if updated == existing:
                return False
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            if log:
                log(f"[brevity] updated {name}\n")
            return True
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(block + "\n")
        if log:
            log(f"[brevity] added brevity block to {name}\n")
        return True
    except OSError as exc:
        if log:
            log(f"[brevity] {name}: {exc}\n")
        return False


def can_compress_memory_file(path):
    name = os.path.basename(path)
    if name.endswith(".original.md"):
        return False
    ext = os.path.splitext(name)[1].lower()
    if ext in BREVITY_DENY_EXT:
        return False
    return ext in BREVITY_ALLOWED_EXT


def split_fenced_regions(text):
    lines = text.splitlines(keepends=True)
    regions = []
    buffer = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            if buffer:
                regions.append(("code" if in_fence else "text", "".join(buffer)))
                buffer = []
            buffer.append(line)
            in_fence = not in_fence
            continue
        buffer.append(line)
    if buffer:
        regions.append(("code" if in_fence else "text", "".join(buffer)))
    return regions


def compress_plain_line(line, level):
    stripped = line.rstrip("\n")
    if not stripped.strip():
        return line
    if stripped.lstrip().startswith(("#", "-", "*", ">")):
        prefix_match = re.match(r"^(\s*[#>\-*]+\s*)", stripped)
        prefix = prefix_match.group(1) if prefix_match else ""
        body = stripped[len(prefix):]
        return prefix + compress_sentence(body, level) + ("\n" if line.endswith("\n") else "")
    if re.match(r"^\s*\d+\.\s+", stripped):
        prefix = re.match(r"^(\s*\d+\.\s+)", stripped).group(1)
        body = stripped[len(prefix):]
        return prefix + compress_sentence(body, level) + ("\n" if line.endswith("\n") else "")
    return compress_sentence(stripped, level) + ("\n" if line.endswith("\n") else "")


def compress_sentence(text, level):
    protected = {}

    def protect(match):
        # Placeholder must be unmatchable by every protection regex below:
        # no backticks (code-span regex), no "http" (URL regex), and no
        # [A-Z_][A-Z0-9_]+ run (ALL-CAPS regex). A previous __GRAFEL_TOKEN_n__
        # scheme matched the ALL-CAPS regex itself, got double-wrapped, and
        # left literal placeholders in the output.
        key = f"\x00grafel:{len(protected)}\x00"
        protected[key] = match.group(0)
        return key

    work = re.sub(r"`[^`]+`", protect, text)
    work = re.sub(r"https?://\S+", protect, work)
    work = re.sub(r"\b[A-Z_][A-Z0-9_]{1,}\b", protect, work)
    for pattern, repl in FILLER_PATTERNS:
        work = pattern.sub(repl, work)
    if level in ("full", "ultra"):
        work = ARTICLE_RE.sub("", work)
    work = work.replace("You should ", "").replace("you should ", "")
    work = work.replace("Remember to ", "").replace("remember to ", "")
    work = SPACE_RE.sub(" ", work).strip(" ,")
    if level == "ultra":
        work = work.replace(" because ", " -> ")
        work = work.replace(" then ", ". ")
    # Restore in reverse insertion order so that, even if a placeholder were
    # ever nested inside a later one, the outer is expanded first.
    for key, value in reversed(list(protected.items())):
        work = work.replace(key, value)
    work = work.strip() or text.strip()
    if work and work[0].isalpha():
        work = work[0].upper() + work[1:]
    return work


def compress_memory_text(text, level=BREVITY_DEFAULT):
    out = []
    for region_type, chunk in split_fenced_regions(text):
        if region_type == "code":
            out.append(chunk)
            continue
        lines = [compress_plain_line(line, level) for line in chunk.splitlines(keepends=True)]
        out.append("".join(lines))
    return "".join(out)


def backup_memory_file(path):
    backup = os.path.splitext(path)[0] + ".original.md"
    shutil.copyfile(path, backup)
    return backup


def compress_memory_file(path, level=BREVITY_DEFAULT):
    if not can_compress_memory_file(path):
        return {"ok": False, "reason": "unsupported"}
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            original = fh.read()
    except OSError as exc:
        return {"ok": False, "reason": str(exc)}
    if not original.strip():
        return {"ok": False, "reason": "empty"}
    compressed = compress_memory_text(original, level)
    if not compressed.strip():
        return {"ok": False, "reason": "empty-output"}
    if compressed == original:
        return {"ok": False, "reason": "no-change"}
    backup = backup_memory_file(path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(compressed)
    except OSError as exc:
        shutil.copyfile(backup, path)
        return {"ok": False, "reason": str(exc), "backup": backup}
    before_tokens, exact_before = count_tokens(original)
    after_tokens, exact_after = count_tokens(compressed)
    return {
        "ok": True,
        "backup": backup,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "saved_tokens": max(0, before_tokens - after_tokens),
        "exact": exact_before and exact_after,
    }


def output_savings_snapshot(claude_usage, codex_usage, copilot_usage, level=BREVITY_DEFAULT):
    reduction = brevity_level_config(level)["output_reduction"]
    claude_output = ((claude_usage or {}).get("totals") or {}).get("out", 0) if claude_usage else 0
    codex_output = (codex_usage or {}).get("output", 0) if codex_usage else 0
    copilot_requests = (copilot_usage or {}).get("turns", 0) if copilot_usage else 0
    copilot_proxy_output = copilot_requests * 180
    total_output = claude_output + codex_output + copilot_proxy_output
    saved = int(total_output * reduction)
    return {
        "level": level,
        "estimated_output_tokens": total_output,
        "estimated_saved_tokens": saved,
        "estimated_saved_percent": int(round(reduction * 100)),
        "claude_output": claude_output,
        "codex_output": codex_output,
        "copilot_proxy_output": copilot_proxy_output,
    }


def brevity_dashboard_lines(stats, prices, level):
    lines = ["\n=== GRAFEL BREVITY MODE ===\n"]
    saved = int(stats.get("brevity_output_saved_tokens_estimate", 0))
    events = int(stats.get("brevity_events", 0))
    memory_saved = int(stats.get("memory_compression_saved_tokens", 0))
    memory_events = int(stats.get("memory_compression_events", 0))
    lines.append(f"Mode: {brevity_level_config(level)['title']}\n")
    lines.append(f"Output tokens estimated saved: ~{saved:,}\n")
    lines.append(f"Brevity measurements recorded: {events}\n")
    lines.append(f"Repo memory compression saved: ~{memory_saved:,} input tokens\n")
    lines.append(f"Memory compression runs: {memory_events}\n")
    lines.append("Estimated output-side cost avoided:\n")
    for model, price in prices.items():
        lines.append(f"   {model}: ~${saved / 1_000_000 * price:.2f}\n")
    lines.append("===========================\n\n")
    return lines


def default_memory_candidates(repo_path):
    return [
        os.path.join(repo_path, "CLAUDE.md"),
        os.path.join(repo_path, "AGENTS.md"),
        os.path.join(repo_path, ".github", "copilot-instructions.md"),
        os.path.join(repo_path, "README.md"),
    ]


def timestamp_slug():
    return datetime.now().strftime("%Y%m%d-%H%M%S")
