"""Deploy VisualProof on StudioNet and seed a board that carries every state.

Run: gltest --network studionet tests/deploy_seed_visualproof.py -v -s

The board it leaves behind:

  1  REQUESTED   visual   open for a visitor to run the attestation
  2  ATTESTED    visual   a standing verdict, challenge window counting down
  3  CHALLENGED  visual   a challenge staked and left for a visitor to re-review
  4  UPHELD      text     a challenge that agreed: bond forfeited to the verifier
  5  OVERTURNED  text     a challenge that flipped the record after a page edit
  6  REFUNDED    text     a page that never rendered: three rounds, fee returned

The one state this cannot seed is REWARDED, because the challenge window is a
real day: once attestation 2's window closes, anyone can call claim_reward and
watch the fee move to the verifier. Every other exit is reachable in one run.

Print the contract address at the end; it goes into the frontend config.
"""

import json
import time
import urllib.request

from gltest import get_accounts, get_contract_factory
from gltest.assertions import tx_execution_succeeded

GEN = 10**18
FEE = GEN // 100        # 0.01 GEN
COOLDOWN = 60           # the contract's REVIEW_COOLDOWN
COOLDOWN_WAIT = COOLDOWN + 8

VISUAL_URL = "https://example.com/"
VISUAL_CLAIM = "The page shows the heading 'Example Domain'."
VISUAL_PURPOSE = "Demonstrating a visual attestation on a page that renders the same for everyone."

TEXT_CLAIM = "The page contains the marker string"
MARKER = "VISUALPROOF-SEED-MARKER"


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


def _new_webhook_url() -> str:
    req = urllib.request.Request(
        "https://webhook.site/token",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    token = json.loads(urllib.request.urlopen(req, timeout=30).read())["uuid"]
    return f"https://webhook.site/{token}"


def _write_page(url: str, body: str) -> None:
    token = url.rsplit("/", 1)[1]
    req = urllib.request.Request(
        f"https://webhook.site/token/{token}",
        data=json.dumps({"default_content": body, "status": 200}).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req, timeout=30)
    served = urllib.request.urlopen(url, timeout=30).read().decode()
    assert body in served, "the endpoint did not take the content"


def _page_with_marker(text: str) -> str:
    return (
        "DELIVERY PAGE - VisualProof seed\n\n"
        f"{text}\n\n"
        "This page exists so a validator can render it and read one exact string.\n"
        f"The string under judgement is written here as: {MARKER}\n"
    )


def _page_without_marker() -> str:
    return (
        "DELIVERY PAGE - VisualProof seed\n\n"
        "The content that carries the marker has been removed from this page.\n"
        "Nothing here matches the string the claim asks about any more.\n"
    )


class Board:
    def __init__(self, contract, buyer, seller, third):
        self.c = contract
        self.buyer = buyer
        self.seller = seller
        self.third = third

    def request(self, url, claim, purpose, evidence, who=None):
        who = who or self.buyer
        receipt = _retry(
            lambda: self.c.connect(who)
            .request_attestation(args=[url, claim, purpose, evidence])
            .transact(value=FEE, wait_interval=10000, wait_retries=20),
            what=f"request {url[:40]}",
        )
        assert tx_execution_succeeded(receipt)
        return int(self.c.get_stats(args=[]).call()["attestations"])

    def attest(self, aid, who=None):
        who = who or self.seller
        receipt = _retry(
            lambda: self.c.connect(who).attest(args=[aid]).transact(wait_interval=12000, wait_retries=40),
            what=f"attest {aid}",
        )
        assert tx_execution_succeeded(receipt)
        return self.c.get_attestation(args=[aid]).call()

    def challenge(self, aid, grounds, who=None):
        who = who or self.third
        bond = int(self.c.get_attestation(args=[aid]).call()["challenge_bond"])
        receipt = _retry(
            lambda: self.c.connect(who)
            .challenge(args=[aid, grounds])
            .transact(value=bond, wait_interval=10000, wait_retries=20),
            what=f"challenge {aid}",
        )
        assert tx_execution_succeeded(receipt)

    def re_review(self, aid, who=None):
        who = who or self.buyer
        receipt = _retry(
            lambda: self.c.connect(who).re_review(args=[aid]).transact(wait_interval=12000, wait_retries=40),
            what=f"re_review {aid}",
        )
        assert tx_execution_succeeded(receipt)
        return self.c.get_attestation(args=[aid]).call()

    def refund_stale(self, aid, who=None):
        who = who or self.third
        receipt = _retry(
            lambda: self.c.connect(who).refund_stale(args=[aid]).transact(wait_interval=10000, wait_retries=20),
            what=f"refund {aid}",
        )
        assert tx_execution_succeeded(receipt)


def test_seed():
    accounts = get_accounts()
    buyer, seller, third = accounts[0], accounts[1], accounts[2]

    c = get_contract_factory("VisualProof").deploy(account=buyer)
    print(f"\nVisualProof deployed at {c.address}")
    board = Board(c, buyer, seller, third)

    # ---- 1: open request, left for a visitor ------------------------------
    open_id = board.request(
        VISUAL_URL,
        VISUAL_CLAIM,
        "Left open on purpose: run the attestation from the app to watch consensus work.",
        "visual",
    )
    print(f"attestation {open_id} REQUESTED (visual, open for anyone)")

    # ---- 2: a clean visual verdict ----------------------------------------
    a2 = board.attest(
        board.request(
            VISUAL_URL,
            VISUAL_CLAIM,
            VISUAL_PURPOSE,
            "visual",
        )
    )
    print(f"attestation {a2['id']}: status={a2['status']} verdict={a2['verdict']}")
    print(f"  evidence: {str(a2['reasoning'])[:200]}")
    assert a2["status"] == "ATTESTED", (
        f"the visual path did not reach a verdict ({a2['status']}). "
        "Run tests/smoke_vision.py first: if vision does not reach consensus, "
        "nothing downstream can."
    )

    # ---- 3: a verdict with a challenge standing on it ---------------------
    a3_id = board.request(VISUAL_URL, VISUAL_CLAIM, "A challenge left standing so a visitor can re-review it.", "visual")
    a3 = board.attest(a3_id)
    assert a3["status"] == "ATTESTED", f"expected ATTESTED, got {a3['status']}"
    board.challenge(a3_id, "The heading may not be visible on every render.")
    a3 = c.get_attestation(args=[a3_id]).call()
    assert a3["status"] == "CHALLENGED", f"expected CHALLENGED, got {a3['status']}"
    print(f"attestation {a3_id} CHALLENGED with {int(a3['challenge_bond']) / GEN} GEN staked")

    # ---- 4: challenge staked, re-review agrees: UPHELD --------------------
    url4 = _new_webhook_url()
    _write_page(url4, _page_with_marker("The work is complete and the marker is present."))
    a4_id = board.request(url4, f"{TEXT_CLAIM} {MARKER}.", "Seeding an upheld challenge.", "text")
    a4 = board.attest(a4_id)
    assert a4["verdict"] == "CONFIRMED", f"expected CONFIRMED, got {a4['verdict']}"
    board.challenge(a4_id, "The marker might have been removed.")
    print(f"attestation {a4_id}: waiting out the {COOLDOWN}s review cooldown...")
    time.sleep(COOLDOWN_WAIT)
    a4 = board.re_review(a4_id)
    assert a4["status"] == "UPHELD", f"expected UPHELD, got {a4['status']}"
    print(f"attestation {a4_id} UPHELD: the challenger's bond paid the verifier")

    # ---- 5: challenge staked, page edited, re-review flips: OVERTURNED -----
    url5 = _new_webhook_url()
    _write_page(url5, _page_with_marker("The work is complete and the marker is present."))
    a5_id = board.request(url5, f"{TEXT_CLAIM} {MARKER}.", "Seeding an overturned challenge.", "text")
    a5 = board.attest(a5_id)
    assert a5["verdict"] == "CONFIRMED", f"expected CONFIRMED, got {a5['verdict']}"
    board.challenge(a5_id, "The claim was true when it was judged; the page has changed since.")
    # the page is rewritten in place, so the SAME url now fails the same claim
    _write_page(url5, _page_without_marker())
    print(f"attestation {a5_id}: the page was edited in place; waiting out the cooldown...")
    time.sleep(COOLDOWN_WAIT)
    a5 = board.re_review(a5_id)
    assert a5["status"] == "OVERTURNED", f"expected OVERTURNED, got {a5['status']}"
    print(f"attestation {a5_id} OVERTURNED: fee back to the requester, bond back to the challenger")

    # ---- 6: a page that never renders: three rounds then REFUNDED ---------
    dead_url = "https://visualproof-seed-host-that-never-resolves.invalid/"
    a6_id = board.request(dead_url, "The page shows anything at all.", "Demonstrating the force-refund path.", "text")
    for i in range(2):
        a6 = board.attest(a6_id)
        print(f"  attempt {i + 1}: {a6['status']} (round {int(a6['rounds'])})")
        time.sleep(COOLDOWN_WAIT)
    a6 = board.attest(a6_id)
    assert a6["status"] == "REFUNDED", f"expected REFUNDED after three rounds, got {a6['status']}"
    print(f"attestation {a6_id} REFUNDED: the fee went back after three unrenderable rounds")

    # ---- accounting across the board --------------------------------------
    s = c.get_stats(args=[]).call()
    held = int(s["held"])
    bonds = int(s["bonds_held"])
    rewarded = int(s["rewarded"])
    refunded = int(s["refunded"])
    bond_payouts = int(s["bond_payouts"])
    print(
        f"\nFINAL stats: attestations={s['attestations']} attested={s['attested']} "
        f"confirmed={s['confirmed']} refuted={s['refuted']} challenged={s['challenged']} "
        f"overturned={s['overturned']} void_rounds={s['void_rounds']}"
    )
    print(
        f"money: held={held / GEN} GEN bonds_held={bonds / GEN} GEN "
        f"rewarded={rewarded / GEN} GEN refunded={refunded / GEN} GEN "
        f"bond_payouts={bond_payouts / GEN} GEN"
    )

    # every fee is either still held, paid out, or refunded
    fees_in = int(s["attestations"]) * FEE
    assert held + rewarded + refunded == fees_in, (
        f"fee accounting broken: held({held}) + rewarded({rewarded}) + refunded({refunded}) != {fees_in}"
    )
    # the standing challenge's bond is the only bond still inside
    assert bonds == FEE, f"expected one standing bond of {FEE}, got {bonds}"

    print(f"\nVISUALPROOF_ADDRESS={c.address}")
    print("SEED DONE")


if __name__ == "__main__":
    test_seed()
