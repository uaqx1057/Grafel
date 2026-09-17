import os
import re


def count_tokens(text):
    """Exact token count via tiktoken if available; else ~4 chars/token."""
    try:
        import tiktoken  # type: ignore
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), True
    except Exception:
        return max(1, len(text) // 4), False


def iter_code_files(path, code_ext, skip_dirs, max_file_size=2_000_000):
    """Yield readable code-like files under a repo, skipping noisy folders."""
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in names:
            if os.path.splitext(name)[1].lower() not in code_ext:
                continue
            fp = os.path.join(root, name)
            try:
                if os.path.getsize(fp) > max_file_size:
                    continue
            except OSError:
                continue
            yield fp


def repo_token_stats(path, code_ext, skip_dirs, token_counter=count_tokens):
    """Return token totals for all code-like files in a repo."""
    repo_tokens, files, exact = 0, 0, True
    for fp in iter_code_files(path, code_ext, skip_dirs):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                t, ex = token_counter(f.read())
        except OSError:
            continue
        repo_tokens += t
        exact = exact and ex
        files += 1
    return {"tokens": repo_tokens, "files": files, "exact": exact}


def graph_token_stats(path, token_counter=count_tokens):
    graph_json = os.path.join(path, "graphify-out", "graph.json")
    if not os.path.exists(graph_json):
        return {"tokens": 0, "exists": False}
    try:
        with open(graph_json, encoding="utf-8", errors="ignore") as f:
            tokens, _ = token_counter(f.read())
    except OSError:
        return {"tokens": 0, "exists": False}
    return {"tokens": tokens, "exists": True}


# Common question words that appear in nearly every source file ("does",
# "work", ...) — counting them as keywords makes the WITHOUT baseline match
# ~the whole repo. Small deliberate list, not an NLP pipeline.
QUESTION_STOPWORDS = {
    "does", "work", "works", "working", "what", "where", "when", "which",
    "this", "that", "these", "those", "with", "from", "into", "have", "will",
    "your", "about", "there", "their", "would", "could", "should", "them",
    "then", "than", "some", "here", "also", "like", "want", "need", "used",
    "using",
}


def question_keywords(question):
    words = [w.lower() for w in re.findall(r"[A-Za-z_]{4,}", question or "")]
    return [w for w in words if w not in QUESTION_STOPWORDS]


def question_file_matches(keywords, text_lower):
    """A file counts as a WITHOUT-baseline match only when it hits at least 2
    distinct keywords (or all of them, for single-keyword questions) — a
    single stray word appearing anywhere is not a plausible grep hit."""
    kws = set(keywords)
    if not kws:
        return True  # no usable keywords: keep the old match-everything upper bound
    need = min(2, len(kws))
    hits = sum(1 for k in kws if k in text_lower)
    return hits >= need


def question_match_stats(path, question, code_ext, skip_dirs, token_counter=count_tokens):
    """Measure an upper-bound grep+read baseline for a codebase question."""
    kws = question_keywords(question)
    without_tokens, matched, exact = 0, 0, True
    for fp in iter_code_files(path, code_ext, skip_dirs):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                txt = f.read()
        except OSError:
            continue
        if question_file_matches(kws, txt.lower()):
            t, ex = token_counter(txt)
            without_tokens += t
            exact = exact and ex
            matched += 1
    return {"tokens": without_tokens, "matched": matched, "exact": exact}


def savings_report_lines(repo_tokens, files, exact, graph_tokens, query_tokens, prices):
    ratio = repo_tokens / graph_tokens if graph_tokens else 0
    method = "exact (tiktoken)" if exact else "estimated (~4 chars/token)"
    lines = [
        "\n",
        "=== GRAFEL SAVINGS REPORT ===\n",
        f"Token count method: {method}\n",
        f"Codebase (full context): ~{repo_tokens:,} tokens across {files} files\n",
    ]
    if graph_tokens:
        lines.append(
            f"Grafel graph index:      ~{graph_tokens:,} tokens"
            f"  ({ratio:.1f}x smaller than the full codebase)\n"
        )
    lines.append(f"Per scoped question:     ~{query_tokens:,} tokens (graph query, capped)\n")
    lines.append("\n-- Real cost to put the WHOLE codebase in context once --\n")
    lines.append("   (input tokens x published model price; edit prices in ~/.grafel.json)\n")
    for model, price in prices.items():
        lines.append(f"   {model} (in ${price:.2f}/M):  ${repo_tokens / 1_000_000 * price:.2f}\n")
    lines.append("\n-- Per 100 codebase questions (illustrative) --\n")
    naive_per_q = min(repo_tokens, 30_000)
    for model, price in prices.items():
        without = 100 * naive_per_q / 1_000_000 * price
        with_ = 100 * query_tokens / 1_000_000 * price
        cut = (1 - (query_tokens / naive_per_q)) * 100 if naive_per_q else 0
        lines.append(
            f"   {model}: without Grafel ~${without:.2f}  ->  "
            f"with Grafel ~${with_:.2f}   (~{cut:.0f}% less)\n"
        )
    lines.append(
        f"   (assumes ~{naive_per_q:,} tokens/question exploring files "
        f"vs ~{query_tokens:,} via the graph; adjust to your own workload)\n"
    )
    lines.append("=============================\n\n")
    return lines


def ab_report_lines(question, exact, without_tokens, matched, with_tokens, prices):
    method = "exact (tiktoken)" if exact else "estimated (~4 chars/token)"
    cut = (1 - with_tokens / without_tokens) * 100 if without_tokens else 0
    lines = [
        "\n",
        f'=== GRAFEL A/B TEST: "{question}" ===\n',
        f"Token count method: {method}\n",
        f"WITHOUT Grafel (upper bound: agent greps + reads {matched} keyword-matching files): ~{without_tokens:,} tokens\n",
        f"WITH Grafel (one graph query):                               ~{with_tokens:,} tokens\n",
        f"Reduction on THIS question: ~{cut:.0f}% fewer tokens\n",
        "\n-- Real cost of THIS question (input tokens x model price) --\n",
    ]
    for model, price in prices.items():
        wo = without_tokens / 1_000_000 * price
        wi = with_tokens / 1_000_000 * price
        lines.append(f"   {model}: without ~${wo:.4f}  ->  with ~${wi:.4f}\n")
    lines.append("   (WITHOUT = UPPER BOUND: grep+read of files hitting >=2 distinct keywords;\n")
    lines.append("    WITH = the actual graph query answer. Ask more questions to compare.)\n")
    lines.append("=============================\n\n")
    return lines


def prompt_comparison_lines(without_tokens, matched, with_tokens, prices):
    cut = (1 - with_tokens / without_tokens) * 100 if without_tokens else 0
    frac = (with_tokens / without_tokens) if without_tokens else 0
    full = 26
    fill = max(1, int(round(frac * full))) if with_tokens else 0
    lines = [
        "\n── THIS PROMPT :: COST COMPARISON ──\n",
        f"WITHOUT Grafel: ~{without_tokens:,} tokens (upper bound: agent greps + reads {matched} files)\n",
        f"WITH Grafel:    ~{with_tokens:,} tokens (one graph query)\n",
        "WITHOUT [" + "█" * full + "]\n",
        "WITH    [" + "█" * fill + "░" * (full - fill) + "]\n",
        f"Saved: ~{cut:.0f}% fewer tokens on this prompt\n",
    ]
    for model, price in prices.items():
        lines.append(
            f"   {model}: ~${without_tokens / 1e6 * price:.4f}  ->  "
            f"~${with_tokens / 1e6 * price:.4f}\n"
        )
    return lines


def reduction_percent(without_tokens, with_tokens):
    return (1 - with_tokens / without_tokens) * 100 if without_tokens else 0

