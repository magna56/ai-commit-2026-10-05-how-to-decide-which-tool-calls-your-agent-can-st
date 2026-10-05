"""Which tool calls can your agent stop waiting for, and what it costs when you guess.

Pure Python, no dependencies, no network, no API key. The loop is simulated so
the timing is deterministic, but the scheduling rule is the real one: a detached
call overlaps the model's generation, a blocking call does not.

Three policies run against the same request. The point is that the aggressive
policy is faster AND wrong, so wall-clock alone cannot tell you if you were right.
"""

GEN_PER_STEP = 0.4      # seconds the model spends generating one step
VERDICT = {True: "correct", False: "WRONG"}


class Tool:
    def __init__(self, name, secs, writes=False):
        self.name, self.secs, self.writes = name, secs, writes

    def __repr__(self):
        return self.name


# One request: "quote these three SKUs, total them, and state the return policy."
QUOTE_A = Tool("get_quote(a)", 3.0)
QUOTE_B = Tool("get_quote(b)", 2.5)
QUOTE_C = Tool("get_quote(c)", 4.0)
POLICY = Tool("get_policy", 0.2)
ORDER = Tool("place_order", 1.5, writes=True)

# The plan the model follows: (step, tool it calls, tools its text needs first)
PLAN = [
    ("call the three quote lookups", [QUOTE_A, QUOTE_B, QUOTE_C], []),
    ("state the return policy", [POLICY], [POLICY]),
    ("total the three quotes", [], [QUOTE_A, QUOTE_B, QUOTE_C]),
    ("place the order", [ORDER], [ORDER]),
]

POLICIES = {
    "block everything": lambda t: False,
    "detach independent reads": lambda t: not t.writes and t is not POLICY,
    "detach every read": lambda t: not t.writes,
    "detach everything": lambda t: True,
}


def run(detach):
    """Walk the plan on a clock. Returns (seconds, wrong_steps, log).

    The scheduling rule that matters: a detached call does NOT remove the wait,
    it moves the wait from the call site to the first step that needs the result.
    If no step needs it, the wait never happens. If the step that needs it is the
    step that issued it, the model has already written its text -- and that is
    the only way detaching produces a wrong answer rather than a slower one.
    """
    now, log, wrong = 0.0, [], []
    landing, issued_at = {}, {}

    for step, (label, calls, needs) in enumerate(PLAN):
        for t in calls:
            issued_at[t] = step
            if detach(t):
                landing[t] = now + t.secs        # runs alongside generation
                log.append(f"      detach {t.name:<14} lands at {landing[t]:5.1f}s")
            else:
                now += t.secs                    # the model waits right here
                landing[t] = now
                log.append(f"      block  {t.name:<14} done at  {now:5.1f}s")

        # Deliver what this step needs. A result issued in an EARLIER step can be
        # waited for and handed over; one issued in THIS step cannot.
        unavailable = [t for t in needs if issued_at.get(t) == step and detach(t)]
        for t in needs:
            if t not in unavailable:
                now = max(now, landing.get(t, now))

        now += GEN_PER_STEP                      # the model writes this step

        if unavailable:
            wrong.append((label, unavailable))
            log.append(f"    ! {label}: written at {now:4.1f}s without {unavailable}")
        else:
            log.append(f"      {label}: written at {now:4.1f}s")

    return now, wrong, log


def main():
    print("ASYNC TOOL CALLING: three policies, one request\n")
    print(f"  plan: {len(PLAN)} steps, {GEN_PER_STEP}s of generation each")
    print("  tools: " + ", ".join(f"{t.name} {t.secs}s" + ("*write" if t.writes else "")
                                  for t in (QUOTE_A, QUOTE_B, QUOTE_C, POLICY, ORDER)))

    rows = []
    for name, detach in POLICIES.items():
        secs, wrong, log = run(detach)
        rows.append((name, secs, wrong))
        print(f"\n  --- {name}")
        for line in log:
            print(line)

    base = rows[0][1]
    print("\n  SUMMARY")
    print(f"    {'policy':<26}{'wall-clock':>11}{'saved':>8}{'steps wrong':>13}  verdict")
    for name, secs, wrong in rows:
        print(f"    {name:<26}{secs:>10.1f}s{base - secs:>7.1f}s{len(wrong):>13}  "
              f"{VERDICT[not wrong]}")

    fastest = min(rows, key=lambda r: r[1])
    safest = [r for r in rows if not r[2]]
    best = min(safest, key=lambda r: r[1])

    print(f"\n    fastest policy : {fastest[0]} ({fastest[1]:.1f}s)")
    print(f"    fastest CORRECT: {best[0]} ({best[1]:.1f}s)")
    if fastest[0] != best[0]:
        print("    -> the fastest policy is not the correct one")

    print("\n  WHY THE AGGRESSIVE POLICY IS WRONG")
    for name, _, wrong in rows:
        for label, missing in wrong:
            print(f"    {name}: '{label}' needed {missing} and did not have it")

    print("""
  READ IT THIS WAY
    Detaching never deletes a wait. It moves the wait to the first step that
    needs the result, which is why the three quote lookups pay off: they are
    issued in step 1 and needed in step 3, so their time overlaps two steps of
    generation. Duration decides nothing. get_policy is the fastest tool here
    and must still block, because the step that calls it is the step that quotes
    it -- there is no later request to deliver into. place_order is worse: the
    model reports an order it never saw confirmed.

    Sort tools by DEPENDENCY DISTANCE, not by how slow they are. Then drop any
    that write. Wall-clock is the reward and never the test.""")


if __name__ == "__main__":
    main()
