# How to Decide Which Tool Calls Your Agent Can Stop Waiting For

**TL;DR:** A model can issue a tool call and keep generating instead of waiting for the result. The risk moves from latency to ordering: the answer can be written before the fact that would have changed it arrives.

Published from [The AI Commit](https://theaicommit.com/#2026-10-05/code) — Building Agents & MCP, 2026-10-05.

## Run

```bash
python3 code_example.py
```

## Output

```
ASYNC TOOL CALLING: three policies, one request

  plan: 4 steps, 0.4s of generation each
  tools: get_quote(a) 3.0s, get_quote(b) 2.5s, get_quote(c) 4.0s, get_policy 0.2s, place_order 1.5s*write

  --- block everything
      block  get_quote(a)   done at    3.0s
      block  get_quote(b)   done at    5.5s
      block  get_quote(c)   done at    9.5s
      call the three quote lookups: written at  9.9s
      block  get_policy     done at   10.1s
      state the return policy: written at 10.5s
      total the three quotes: written at 10.9s
      block  place_order    done at   12.4s
      place the order: written at 12.8s

  --- detach independent reads
      detach get_quote(a)   lands at   3.0s
      detach get_quote(b)   lands at   2.5s
      detach get_quote(c)   lands at   4.0s
      call the three quote lookups: written at  0.4s
      block  get_policy     done at    0.6s
      state the return policy: written at  1.0s
      total the three quotes: written at  4.4s
      block  place_order    done at    5.9s
      place the order: written at  6.3s

  --- detach every read
      detach get_quote(a)   lands at   3.0s
      detach get_quote(b)   lands at   2.5s
      detach get_quote(c)   lands at   4.0s
      call the three quote lookups: written at  0.4s
      detach get_policy     lands at   0.6s
    ! state the return policy: written at  0.8s without [get_policy]
      total the three quotes: written at  4.4s
      block  place_order    done at    5.9s
      place the order: written at  6.3s

  --- detach everything
      detach get_quote(a)   lands at   3.0s
      detach get_quote(b)   lands at   2.5s
      detach get_quote(c)   lands at   4.0s
      call the three quote lookups: written at  0.4s
      detach get_policy     lands at   0.6s
    ! state the return policy: written at  0.8s without [get_policy]
      total the three quotes: written at  4.4s
      detach place_order    lands at   5.9s
    ! place the order: written at  4.8s without [place_order]

  SUMMARY
    policy                     wall-clock   saved  steps wrong  verdict
    block everything                12.8s    0.0s            0  correct
    detach independent reads         6.3s    6.5s            0  correct
    detach every read                6.3s    6.5s            1  WRONG
    detach everything                4.8s    8.0s            2  WRONG

    fastest policy : detach everything (4.8s)
    fastest CORRECT: detach independent reads (6.3s)
    -> the fastest policy is not the correct one

  WHY THE AGGRESSIVE POLICY IS WRONG
    detach every read: 'state the return policy' needed [get_policy] and did not have it
    detach everything: 'state the return policy' needed [get_policy] and did not have it
    detach everything: 'place the order' needed [place_order] and did not have it

  READ IT THIS WAY
    Detaching never deletes a wait. It moves the wait to the first step that
    needs the result, which is why the three quote lookups pay off: they are
    issued in step 1 and needed in step 3, so their time overlaps two steps of
    generation. Duration decides nothing. get_policy is the fastest tool here
    and must still block, because the step that calls it is the step that quotes
    it -- there is no later request to deliver into. place_order is worse: the
    model reports an order it never saw confirmed.

    Sort tools by DEPENDENCY DISTANCE, not by how slow they are. Then drop any
    that write. Wall-clock is the reward and never the test.

```

## Code

See [`code_example.py`](code_example.py).
