import os

from grafel_core.live import initial_meter_sessions, refresher_sessions, session_in_scope


def meter_start_state(
    repo_path,
    scope_mode,
    find_workspace_for,
    parse_workspace_folders,
    claude_log_dir,
    list_ai_sessions,
    session_cwd_fast,
):
    meter = initial_meter_sessions(
        repo_path,
        scope_mode,
        find_workspace_for,
        parse_workspace_folders,
        claude_log_dir,
        list_ai_sessions,
        session_cwd_fast,
    )
    return {
        "mode": scope_mode,
        "scope": meter["scope_state"]["scope"],
        "dirs": meter["scope_state"]["dirs"],
        "folders": meter["scope_state"]["folders"],
        "scope_state": meter["scope_state"],
        "sessions": meter["sessions"],
        "other_sessions": meter["other_sessions"],
        "all_sessions": meter["all_sessions"],
        "has_any": meter["has_any"],
        "in_scope_count": meter["in_scope_count"],
        "out_of_scope_count": meter["out_of_scope_count"],
        "all_counts": meter["all_counts"],
        "in_scope_counts": meter["in_scope_counts"],
        "out_of_scope_counts": meter["out_of_scope_counts"],
    }


def meter_fallback_message(scope_folders):
    scope_word = "workspace" if len(scope_folders) > 1 else "repo"
    return (
        "Grafel Live Meter",
        f"No AI sessions found for this {scope_word} yet.\n\n"
        "Open Claude Code, Codex, or Copilot Chat in this project and send a prompt "
        "or click YES to show ALL sessions on this machine instead.",
    )


def meter_machine_sessions_message(scope_folders, out_of_scope_count, out_of_scope_counts):
    scope_word = "workspace" if len(scope_folders) > 1 else "repo"
    parts = []
    if out_of_scope_counts.get("claude"):
        parts.append(f"{out_of_scope_counts['claude']} Claude")
    if out_of_scope_counts.get("codex"):
        parts.append(f"{out_of_scope_counts['codex']} Codex")
    if out_of_scope_counts.get("copilot"):
        parts.append(f"{out_of_scope_counts['copilot']} Copilot")
    if out_of_scope_counts.get("other"):
        parts.append(f"{out_of_scope_counts['other']} other")
    detail = ", ".join(parts) if parts else f"{out_of_scope_count} AI sessions"
    return (
        "Grafel Live Meter",
        f"No AI sessions belong to this {scope_word} right now.\n\n"
        f"Grafel did find {out_of_scope_count} machine-wide session(s): {detail}.\n\n"
        "Click YES to monitor all machine sessions, or NO to keep the meter repo-focused.",
    )


def meter_unscoped_console_notice():
    return (
        "\nNo AI sessions exist for THIS repo yet - showing ALL sessions on this machine instead.\n"
        "Open Claude Code, Codex, or Copilot Chat in this folder and send one prompt to get a tab for it.\n",
        "dim",
    )


def copilot_apply_events(requests, events):
    reqs = [dict(r) for r in requests]

    def ensure(index):
        while len(reqs) <= index:
            reqs.append({"text": "", "pt": 0, "ct": 0, "cr": 0.0})

    def flush_batch(texts):
        # Defensive handling for kind==2 events (KNOWN_ISSUES point 9, item 12).
        # iter_vscode_chat_events emits ("request", None, text) for a kind==2
        # patch on ["requests"], but no real captured fixture confirms whether
        # that patch APPENDS new items or RESENDS the full array (kind==1's
        # "set value at path k" semantics suggest the latter, which naive
        # appending would duplicate). Safe under either interpretation: if a
        # prefix of the batch matches the current tail of reqs by text, treat
        # that prefix as a resend of already-known items and append only the
        # genuinely new suffix. When nothing matches (the true-append case)
        # every item is appended, exactly as before.
        skip = 0
        for n in range(min(len(texts), len(reqs)), 0, -1):
            prefix = texts[:n]
            if all(prefix) and [r["text"] for r in reqs[-n:]] == prefix:
                skip = n
                break
        for txt in texts[skip:]:
            reqs.append({"text": txt, "pt": 0, "ct": 0, "cr": 0.0})

    pending = []
    for ev in events:
        if ev[0] == "request" and ev[1] is None:
            pending.append(ev[2] or "")
            continue
        if pending:
            flush_batch(pending)
            pending = []
        if ev[0] == "request":
            idx = ev[1]
            ensure(idx)
            if ev[2]:
                reqs[idx]["text"] = ev[2]
        else:
            _, idx, fld, val = ev
            if not isinstance(idx, int):
                continue
            ensure(idx)
            key = {"promptTokens": "pt", "completionTokens": "ct", "copilotCredits": "cr"}[fld]
            reqs[idx][key] = val or 0
    if pending:
        flush_batch(pending)
    return reqs


def copilot_ready_indexes(requests, printed, replayed, idle_seconds):
    ready = []
    if not replayed:
        return list(range(printed, len(requests)))
    while printed < len(requests) - 1:
        ready.append(printed)
        printed += 1
    if printed < len(requests) and idle_seconds > 8 and (requests[printed]["pt"] or requests[printed]["ct"]):
        ready.append(printed)
    return ready


# Minimum cache-read tokens per request before a prompt can count as "proven"
# saved or feed the unwired baseline. A cache-cold turn (session start, post-
# compaction) has cr ~= 0, which would otherwise always beat the proven
# threshold and fabricate savings. Matches the floor claude_baseline_update
# has always used.
PROVEN_CR_FLOOR = 10_000


def classify_claude_model(model):
    """Classify a Claude model id string into a CLAUDE_RATES pricing class.
    Same matching logic scan_claude_usage uses (sessions.py)."""
    m = (model or "").lower()
    return ("opus" if "opus" in m else
            "sonnet" if "sonnet" in m else
            "haiku" if "haiku" in m else "other")


def prices_for_model(model, rates):
    """Pick the per-model price dict (keys in/cw/cr/out) for a usage bucket's
    model id, falling back to the 'other' class."""
    cls = classify_claude_model(model)
    return dict(rates.get(cls) or rates["other"])


def prompt_recording_decision(caught_up, proven, saved_tokens):
    """Decide whether a completed prompt's savings may be PERSISTED now.

    Strategy (a) from KNOWN_ISSUES #1: the historical replay pass (meter start,
    or a new/resumed chat file whose jsonl re-contains the prior transcript)
    must be side-effect-free. Only prompts that complete after the tailer has
    caught up to live (`caught_up is True`) may record realized savings or feed
    the unwired baseline. Tradeoff (accepted): a prompt completed while the
    meter was OFF between two meter sessions is never counted.
    """
    live = bool(caught_up)
    return {
        "record_saved": live and bool(proven) and saved_tokens > 0,
        "update_baseline": live,
    }


def claude_prompt_summary(state, bucket, base_cr, wired_now, fraction, prices):
    if not bucket or not bucket["msgs"]:
        return None
    next_state = dict(state)
    next_state["n"] += 1
    next_state["reqs"] += bucket["msgs"]
    tok = bucket["in"] + bucket["cr"] + bucket["cw"] + bucket["out"]
    next_state["tok"] += tok
    cr_cost = bucket["cr"] / 1e6 * prices["cr"]
    real = (
        bucket["in"] / 1e6 * prices["in"]
        + bucket["cw"] / 1e6 * prices["cw"]
        + cr_cost
        + bucket["out"] / 1e6 * prices["out"]
    )
    cr_resp = bucket["cr"] / max(1, bucket["msgs"])
    next_state["cost"] += real
    proven = False
    saved_tokens = 0
    realized = 0.0
    opp_tok = 0
    if wired_now and base_cr and cr_resp > PROVEN_CR_FLOOR and cr_resp < base_cr * 0.85:
        saved_tokens = int((base_cr - cr_resp) * bucket["msgs"])
        realized = saved_tokens / 1e6 * prices["cr"]
        next_state["realized"] += realized
        next_state["saved_tok"] += saved_tokens
        proven = True
    else:
        opp_tok = int(bucket["cr"] * fraction)
        next_state["opp"] += cr_cost * fraction
        next_state["opp_tok"] += opp_tok
    return {
        "state": next_state,
        "token_total": tok,
        "real_cost": real,
        "cache_read_cost": cr_cost,
        "cache_read_per_request": cr_resp,
        "proven": proven,
        "saved_tokens": saved_tokens,
        "realized": realized,
        "recoverable_tokens": opp_tok,
    }


def claude_baseline_update(baselines, key, wired_now, cache_read_per_request):
    if not key or wired_now or cache_read_per_request <= PROVEN_CR_FLOOR:
        return baselines, None
    updated = dict(baselines)
    current = dict(updated.get(key, {"cr": 0.0, "n": 0}))
    current["cr"] = (current["cr"] * current["n"] + cache_read_per_request) / (current["n"] + 1)
    current["n"] += 1
    updated[key] = current
    return updated, current


def seed_baseline_if_missing(baselines, key, repo_tokens):
    """Seed an estimated cache-read baseline for a repo that has never had a live
    UNWIRED session measured (e.g. wired from day one, so claude_baseline_update
    never gets a chance to record one and 'proven' stays unreachable forever).

    Uses the same naive-per-question assumption the Savings Report already uses
    (min(repo_tokens, 30_000) — see savings.savings_report_lines' naive_per_q) as
    a stand-in for 'tokens a normal unwired agent turn would carry'. Recorded with
    n=0 and estimated=True so the first real unwired sample (if one ever comes in)
    replaces it outright rather than being averaged into it.
    """
    if not key or key in baselines or not repo_tokens:
        return baselines, None
    updated = dict(baselines)
    seeded = {"cr": float(min(repo_tokens, 30_000)), "n": 0, "estimated": True}
    updated[key] = seeded
    return updated, seeded


def meter_refresh_sessions(
    scope_state,
    parse_workspace_folders,
    list_ai_sessions,
    session_cwd_fast,
):
    return refresher_sessions(
        scope_state,
        parse_workspace_folders,
        list_ai_sessions,
        session_cwd_fast,
    )
