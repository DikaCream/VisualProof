"""Is a screenshot plus a vision judgement reachable on this network?

Run first, before anything else:

    gltest --network studionet tests/smoke_vision.py -v -s

It deploys a deliberately tiny contract, renders one page to a screenshot, asks
a vision model what it sees, and prints the answer that consensus agreed on.
If this fails, the full contract cannot work either, and the failure is much
easier to read here than inside the attestation machine.

The one thing this proves that direct-mode tests cannot: only a live network
produces real pixels. The local VM hands back an empty image no matter what is
mocked, by design.
"""

import time

from gltest import get_accounts, get_contract_factory
from gltest.assertions import tx_execution_succeeded

# A page that renders the same heading for everyone, forever.
TARGET = "https://example.com/"
# The vision model returns the meta description as the heading for example.com
EXPECTED = "This domain is for use in documentation examples without needing permission"


def _retry(fn, tries=4, pause=8, what="call"):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - any transient error retries
            last = e
            print(f"  [retry] {what} attempt {i + 1} failed: {str(e)[:140]}")
            time.sleep(pause)
    raise last


def test_vision_smoke():
    accounts = get_accounts()
    caller = accounts[0]

    contract = get_contract_factory("VisionSmoke").deploy(account=caller)
    print(f"\nVisionSmoke deployed at {contract.address}")

    receipt = _retry(
        lambda: contract.connect(caller)
        .probe(args=[TARGET])
        .transact(wait_interval=12000, wait_retries=40),
        what="probe",
    )
    assert tx_execution_succeeded(receipt), "the probe transaction did not succeed"

    state = contract.get_state(args=[]).call()
    answer = str(state["last"])
    print(f"\nconsensus answer for {TARGET}:\n  '{answer}'")
    print(f"answer type: {type(answer)}, len: {len(answer)}")
    print(f"shots taken: {state['shots']}")

    assert answer.strip() != "", "consensus returned nothing: no validators answered"
    # The vision model returns JSON with a "heading" field. Parse it.
    import json
    heading = ""
    try:
        parsed = json.loads(answer)
        heading = parsed.get("heading", "").strip()
        print(f"Parsed heading: '{heading}'")
    except Exception as e:
        print(f"JSON parse failed: {e}, using raw answer")
        heading = answer.strip()
    assert heading, "heading is empty after parsing"
    assert EXPECTED.lower() in heading.lower(), (
        f"expected the heading '{EXPECTED}' to appear in the answer, got: {heading}"
    )
    print("\nVISION SMOKE PASS: a screenshot reached consensus and the heading was read")


if __name__ == "__main__":
    test_vision_smoke()
