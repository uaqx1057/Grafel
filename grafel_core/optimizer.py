def build_optimizer_plan(
    claude_usage,
    codex_usage,
    copilot_usage,
    repo_has_graph,
    claude_rates,
    query_tokens,
):
    recs = []
    claude_summary = None
    if claude_usage and claude_usage.get("responses"):
        totals = claude_usage["totals"]
        responses = claude_usage["responses"]
        per_model = claude_usage["per_model"]
        months = {k: v for k, v in claude_usage["months"].items() if k != "unknown"}
        recent_key = max(months) if months else None
        lifetime_tokens = sum(totals.values()) or 1
        month_tokens = months.get(recent_key, lifetime_tokens) if recent_key else lifetime_tokens
        month_fraction = month_tokens / lifetime_tokens
        total_cost = 0.0
        by_model = {}
        for cls, pm in per_model.items():
            rate = claude_rates.get(cls, claude_rates["other"])
            cost = (
                pm["in"] / 1e6 * rate["in"]
                + pm["cw"] / 1e6 * rate["cw"]
                + pm["cr"] / 1e6 * rate["cr"]
                + pm["out"] / 1e6 * rate["out"]
            )
            by_model[cls] = cost
            total_cost += cost
        month_cost = total_cost * month_fraction
        avg_cr = totals["cr"] / responses
        avg_out = totals["out"] / responses
        claude_summary = {
            "totals": totals,
            "responses": responses,
            "total_cost": total_cost,
            "month_cost": month_cost,
            "recent_key": recent_key,
            "avg_cr": avg_cr,
            "avg_out": avg_out,
            "by_model": by_model,
        }

        opus = by_model.get("opus", 0.0)
        if opus > 0 and opus / max(total_cost, 1e-9) > 0.20:
            pm = per_model["opus"]
            rate = claude_rates["sonnet"]
            sonnet_equiv = (
                pm["in"] / 1e6 * rate["in"]
                + pm["cw"] / 1e6 * rate["cw"]
                + pm["cr"] / 1e6 * rate["cr"]
                + pm["out"] / 1e6 * rate["out"]
            )
            save = max(0.0, (opus - sonnet_equiv) * 0.5) * month_fraction
            recs.append({
                "rank": 1,
                "tag": "MODEL",
                "title": "Default to Sonnet; escalate to Opus only when it's actually stuck",
                "detail": [
                    f"You spent ~${opus:,.2f} on Opus, which is ~5x Sonnet's price.",
                    "Most edits, refactors and codebase Q&A run fine on Sonnet.",
                    "In Claude Code: /model sonnet (switch to opus only for hard bugs).",
                ],
                "save": save,
            })

        if avg_cr > 60_000:
            replaceable = totals["cr"] * 0.25
            save = replaceable / 1e6 * 0.30 * month_fraction
            recs.append({
                "rank": 1,
                "tag": "GRAPH",
                "title": "Query the graph instead of loading files into context",
                "detail": [
                    f"Each response carries ~{int(avg_cr):,} cached context tokens.",
                    f"A scoped graph query answers in ~{query_tokens:,} tokens instead of pulling whole files.",
                    "Wire routing via the Integrations menu, then ask through the graph.",
                ],
                "save": save,
            })

        if totals["cr"] and totals["cw"] > 0.20 * totals["cr"]:
            save = (totals["cw"] * 0.30) / 1e6 * 3.75 * month_fraction
            recs.append({
                "rank": 2,
                "tag": "CACHE",
                "title": "Keep sessions warm - avoid frequent /clear and cold restarts",
                "detail": [
                    f"Cache-write is {totals['cw'] / totals['cr'] * 100:.0f}% of cache-read - you're re-paying to rebuild context often.",
                    "Prompt-cache write costs 12.5x a cache read; reuse it.",
                    "Use /compact instead of /clear, and resume with --continue.",
                ],
                "save": save,
            })

        if avg_out > 1200:
            save = (totals["out"] * 0.35) / 1e6 * 15.0 * month_fraction
            recs.append({
                "rank": 2,
                "tag": "OUTPUT",
                "title": "Ask for diffs/patches, not full-file rewrites",
                "detail": [
                    f"Average output is ~{int(avg_out):,} tokens/response (output is the most expensive token class).",
                    "Request 'show only the changed lines / a unified diff'.",
                    "Cuts output tokens sharply on edit-heavy work.",
                ],
                "save": save,
            })

    if repo_has_graph is False:
        recs.append({
            "rank": 1,
            "tag": "SETUP",
            "title": "Build and wire the graph for the project you're working in",
            "detail": [
                "The open project has no graph yet, so your agent is reading raw files.",
                "Run INITIATE SCAN here, then enable the AI tool checkboxes.",
                "This is the single biggest lever for the numbers above.",
            ],
            "save": 0.0,
        })

    if codex_usage and codex_usage.get("reasoning", 0) > codex_usage.get("output", 0):
        reasoning = codex_usage.get("reasoning", 0)
        out_tok = codex_usage.get("output", 0)
        save = reasoning * 0.4 / 1e6 * 10.0
        recs.append({
            "rank": 2,
            "tag": "CODEX",
            "title": "Lower Codex reasoning effort for routine tasks",
            "detail": [
                f"Reasoning tokens (~{reasoning:,}) exceed answer tokens (~{out_tok:,}) - you're paying to over-think simple work.",
                "Use a medium or low reasoning effort for edits and lookups.",
                "Reserve high reasoning for genuinely hard problems.",
            ],
            "save": save,
        })

    if copilot_usage and not copilot_usage.get("error"):
        months = copilot_usage.get("months", {})
        if months:
            this_month = max(months)
            mreq = months.get(this_month, 0)
            if mreq:
                recs.append({
                    "rank": 3,
                    "tag": "COPILOT",
                    "title": "Spend premium Copilot requests only where they pay off",
                    "detail": [
                        f"~{mreq} premium requests in {this_month} (~${mreq * 0.04:.2f} if beyond your allowance).",
                        "Use the base model for trivial completions; save premium requests for real problems.",
                        "Batch related questions into one request instead of many.",
                    ],
                    "save": mreq * 0.04 * 0.3,
                })

    recs.sort(key=lambda item: (item["rank"], -item["save"]))
    total_save = sum(item["save"] for item in recs)
    return {
        "claude_summary": claude_summary,
        "recommendations": recs,
        "total_save": total_save,
    }
