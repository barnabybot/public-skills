from __future__ import annotations

import math
from datetime import datetime, timezone

FAR_AHEAD_LEAD = 12
PACE_PHRASE = {
    "ahead": "ahead of schedule, pace runs out before reset",
    "on": "on pace",
    "behind": "behind schedule",
}


def pace_vs_reset(used, window_minutes, seconds_left):
    elapsed = 100 * (1 - seconds_left / (window_minutes * 60))
    elapsed = min(100, max(0, elapsed))
    delta = used - elapsed
    if delta > FAR_AHEAD_LEAD:
        return "ahead"
    if delta < -FAR_AHEAD_LEAD:
        return "behind"
    return "on"


def assess_native(observation, model, effort, required, evidence, request, cfg, now):
    result = {"model": model, "effort": effort, "state": "unknown", "reasons": [],
              "evidence": evidence, "windows": [], "future_debit": "unknown",
              "concurrency": "unknown", "native_observation": observation}

    def stop(reason, state="unknown"):
        result["state"] = state
        result["reasons"].append(reason)
        return result

    if observation.get("error"):
        return stop(observation["error"])
    try:
        observed = datetime.fromisoformat(observation["read_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None or not 0 <= (now - observed).total_seconds() <= cfg["max_observation_age_seconds"]:
            return stop("Codex observation stale")
        plan = observation.get("plan")
        if observation.get("account_type") != "chatgpt" or not isinstance(plan, str) or not plan:
            return stop("authenticated ChatGPT plan unknown")
        matches = [row for row in observation["models"] if row["model"] == model]
        if len(matches) != 1 or effort not in matches[0]["efforts"]:
            return stop("exact Codex model/effort absent from authenticated catalogue", "excluded")
        if observation.get("ordinaryUsageAllowed") is not True:
            return stop("Codex ordinary usage unavailable", "excluded")
        buckets = observation["buckets"]
        if not buckets or len({bucket["id"] for bucket in buckets}) != len(buckets):
            return stop("Codex account windows absent or duplicated")
        tight = False
        for bucket in buckets:
            if not bucket["id"] or bucket.get("planType") != plan:
                return stop("Codex account window identity or plan mismatch")
            if bucket.get("spendControlReached") is not False:
                return stop("Codex spend control reached or unknown", "excluded")
            if bucket.get("rateLimitReachedType") is not None:
                return stop("Codex account limit reached", "excluded")
            if not bucket["windows"]:
                return stop("Codex account window unavailable")
            for window in bucket["windows"]:
                used, minutes, reset_epoch = (window[k] for k in ("usedPercent", "windowDurationMins", "resetsAt"))
                if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
                       for v in (used, minutes, reset_epoch)) or not 0 <= used <= 100 or minutes <= 0:
                    return stop("Codex window usage, duration or reset unknown")
                reset = datetime.fromtimestamp(reset_epoch, timezone.utc)
                seconds_left = (reset - now).total_seconds()
                if seconds_left <= 0:
                    return stop("Codex window reset requires a new observation")
                remaining = 100 - used
                label = "weekly" if minutes == 10080 else f"{minutes:g}-minute"
                window_id = f"{bucket['id']}:{window['slot']}"
                if used >= cfg["exhausted_used_percent"]:
                    detail = f"codex {label} {used:g}% used, resets {reset.isoformat()}"
                    result["windows"].append({"id": window_id, "remaining": remaining, "unit": "percent",
                                              "resets_at": reset.isoformat(), "detail": detail})
                    return stop(detail + "; exhausted", "excluded")
                pace = pace_vs_reset(used, minutes, seconds_left)
                detail = f"codex {label} {used:g}% used, {PACE_PHRASE[pace]}, resets {reset.isoformat()}"
                result["windows"].append({"id": window_id, "remaining": remaining, "unit": "percent",
                                          "resets_at": reset.isoformat(), "detail": detail, "pace": pace})
                tight |= pace == "ahead"
        if len({w["id"] for w in result["windows"]}) != len(result["windows"]):
            return stop("duplicate Codex account window")
        probe = observation.get("probe", {})
        if probe.get("model") != model or probe.get("effort") != effort or probe.get("runnable") is not True:
            return stop("exact Codex model/effort runtime probe unverified")
        if probe.get("account_unchanged") is not True:
            return stop("Codex account changed during runtime probe")
        if required - {"shell"} or ("shell" in required and probe.get("shell_verified") is not True):
            return stop("required Codex runtime tool unverified")
    except (KeyError, TypeError, ValueError, OverflowError):
        return stop("invalid native Codex observation")
    if evidence["fit"] not in ("ruling", "measured", "practice"):
        return stop("exact task-fit evidence unavailable")
    bound = request.get("bounded_preference", {})
    if type(bound.get("tasks")) is not int or bound["tasks"] != 1 or not bound.get("task") or not bound.get("source"):
        return stop("numeric debit unknown; one-task bounded preference required")
    result.update(state="eligible", tight=tight,
                  observation={"source": observation["source"], "plan": plan,
                               "observed_at": observation["read_at"], "future_debit": "unknown",
                               "concurrency": "unknown", "window_policy": "all returned account buckets",
                               "access": "authenticated catalogue and exact runtime probe"})
    result["reasons"] = [w["detail"] for w in result["windows"]] + [
        "all returned account buckets checked", "account-wide future debit unknown",
        "one authorised task admitted under bounded native policy", evidence["debit_reason"]]
    return result
