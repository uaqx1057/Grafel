import json

from grafel_core.sessions import is_text_user_content


def trim_text(text, limit=400, ellipsis="..."):
    text = " ".join((text or "").split())
    return text[:limit] + (ellipsis if len(text) > limit else "")


def _claude_text_content(content):
    if isinstance(content, str):
        return content
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
            return block["text"]
    return None


def claude_exchanges(path, limit=200, trim=trim_text):
    exchanges = []
    current_user = None
    current_agent = []
    token_total = 0
    seen_ids = set()

    def close_exchange():
        if current_user is not None:
            usage = f"~{token_total:,} tokens" if token_total else ""
            exchanges.append((trim(current_user), trim(" ".join(current_agent)), usage))

    try:
        fh = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return []
    with fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            message = obj.get("message") or {}
            role = message.get("role")
            if obj.get("type") == "user" and role == "user" and is_text_user_content(message.get("content")):
                text = _claude_text_content(message.get("content"))
                if text:
                    close_exchange()
                    current_user = text
                    current_agent = []
                    token_total = 0
            elif role == "assistant":
                message_id = message.get("id")
                usage = message.get("usage") or {}
                if message_id and usage and message_id not in seen_ids:
                    seen_ids.add(message_id)
                    token_total += sum(
                        usage.get(key) or 0
                        for key in (
                            "input_tokens",
                            "cache_read_input_tokens",
                            "cache_creation_input_tokens",
                            "output_tokens",
                        )
                    )
                for block in message.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                        current_agent.append(block["text"])
    close_exchange()
    return exchanges[:limit]


def copilot_exchanges(path, limit=200, trim=trim_text):
    requests = []

    def ensure(index):
        while len(requests) <= index:
            requests.append({"u": "", "a": [], "pt": 0, "ct": 0, "cr": 0.0})

    def add_response(index, parts):
        ensure(index)
        for part in parts or []:
            if (
                isinstance(part, dict)
                and isinstance(part.get("value"), str)
                and part.get("kind") in (None, "markdownContent")
            ):
                requests[index]["a"].append(part["value"])

    try:
        fh = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return []
    with fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            kind, key, value = obj.get("kind"), obj.get("k"), obj.get("v")
            if kind == 0 and isinstance(value, dict):
                for index, req in enumerate(value.get("requests") or []):
                    ensure(index)
                    requests[index]["u"] = ((req.get("message") or {}).get("text") or "")
                    add_response(index, req.get("response"))
            elif kind == 2 and key == ["requests"] and isinstance(value, list):
                for req in value:
                    requests.append({
                        "u": ((req.get("message") or {}).get("text") or ""),
                        "a": [],
                        "pt": 0,
                        "ct": 0,
                        "cr": 0.0,
                    })
            elif (
                kind == 2 and isinstance(key, list) and len(key) == 3
                and key[0] == "requests" and key[2] == "response"
                and isinstance(key[1], int)
            ):
                add_response(key[1], value)
            elif (
                kind == 1 and isinstance(key, list) and len(key) == 3
                and key[0] == "requests" and isinstance(key[1], int)
            ):
                field = {
                    "promptTokens": "pt",
                    "completionTokens": "ct",
                    "copilotCredits": "cr",
                }.get(key[2])
                if field:
                    ensure(key[1])
                    requests[key[1]][field] = value or 0
    out = []
    for req in requests:
        usage = []
        if req["pt"] or req["ct"]:
            usage.append(f"tokens: prompt {req['pt']:,} | completion {req['ct']:,}")
        if req["cr"]:
            usage.append(f"credits: {req['cr']:.2f}")
        out.append((trim(req["u"]), trim(" ".join(req["a"])), " | ".join(usage)))
    return out[:limit]
