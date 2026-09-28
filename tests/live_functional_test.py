"""Exercise every function of VisualProof on the live network.

Run: gltest --network studionet tests/live_functional_test.py -v -s

Three functions cannot be reached on a freshly seeded board inside one sitting:
`claim_reward`, `refund_stale` and `finalize_challenge` all wait on windows of a
day or more. Waiting a day is not a test, so this script generates a probe copy
of the contract with the same logic and compressed clocks, deploys it, and
exercises every function and every guard for real: real consensus, real renders,
real transfers, real reverts.

Three disciplines this script learned the hard way, all encoded below:

- Writes are sent once and only the receipt poll is retried. Retrying the whole
  send turns one successful state change into a confusing revert, because the
  second attempt finds the work already done.
- Every wait is computed from the timestamp the contract recorded
  (`verdict_at`, `challenged_at`, `requested_at`), never a fixed sleep: a
  compressed window is shorter than the run of guard checks between two steps.
- StudioNet rate limits reads to 30 requests per minute (code -32029), so reads
  are cached until the record is written again and a refusal backs off.

The probe contract is written to contracts/fast_clock_probe.py, renamed
VisualProofFast, and deleted again when the run finishes. The production
contract is never modified.
"""

import json
import re
import time
from pathlib import Path

from genlayer_py.types import TransactionStatus
from gltest import get_accounts, get_contract_factory, get_gl_client
from gltest.assertions import tx_execution_succeeded

GEN = 10**18
FEE = GEN // 100
COOLDOWN = 10          # the probe's REVIEW_COOLDOWN
WINDOW = 60            # the probe's CHALLENGE_WINDOW and ATTEST_WINDOW
SLACK = 5              # the probe's DETACH_SLACK
MARGIN = 6             # seconds to add after a computed deadline
RATE_LIMIT_PAUSE = 22

PROBE = Path("contracts/fast_clock_probe.py")
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""), flush=True)
    return bool(ok)


def need(condition: bool, message: str) -> None:
    """A precondition. If this fails, everything after it would mislead."""
    if not condition:
        print(f"\nPRECONDITION FAILED: {message}", flush=True)
        raise AssertionError(message)


def _retry(fn, tries=5, pause=8, what="call"):
    """Retry the send itself only, never a whole write.

    A refused or transiently failed *send* is safe to repeat, because nothing
    reached the chain. A failed *poll* is not: the transaction may already have
    landed. The split lives in Probe._wait.
    """
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e)
            rate_limited = "rate limit" in msg.lower() or "-32029" in msg
            wait = RATE_LIMIT_PAUSE if rate_limited else pause
            print(f"    [send] {what} attempt {i + 1} failed, waiting {wait}s: {msg[:110]}", flush=True)
            time.sleep(wait)
    raise last


def build_probe() -> None:
    """Same contract, compressed clocks, different class name."""
    src = Path("contracts/visual_proof.py").read_text()
    before = src
    src = src.replace("CHALLENGE_WINDOW = 24 * 3600", f"CHALLENGE_WINDOW = {WINDOW}")
    src = src.replace("ATTEST_WINDOW = 3 * 24 * 3600", f"ATTEST_WINDOW = {WINDOW}")
    src = src.replace("DETACH_SLACK = 3600", f"DETACH_SLACK = {SLACK}")
    src = src.replace("REVIEW_COOLDOWN = 60", f"REVIEW_COOLDOWN = {COOLDOWN}")
    src = src.replace("class VisualProof(gl.Contract):", "class VisualProofFast(gl.Contract):")
    assert src != before, "the probe rewrite did not change anything"
    for const, value in (
        ("CHALLENGE_WINDOW", WINDOW),
        ("ATTEST_WINDOW", WINDOW),
        ("DETACH_SLACK", SLACK),
        ("REVIEW_COOLDOWN", COOLDOWN),
    ):
        assert re.search(rf"^{const} = {value}\b", src, re.M), f"{const} was not compressed"
    PROBE.write_text(src)


def new_webhook() -> str:
    import urllib.request

    req = urllib.request.Request(
        "https://webhook.site/token",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return "https://webhook.site/" + json.loads(urllib.request.urlopen(req, timeout=30).read())["uuid"]


def write_page(url: str, body: str) -> None:
    import urllib.request

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


VISUAL_URL = "https://example.com/"
VISUAL_CLAIM = "The page shows the heading 'Example Domain'."
MARKER = "VISUALPROOF-LIVE-TEST"
TEXT_CLAIM = f"The page contains the marker string {MARKER}."
DEAD_URL = "https://visualproof-live-test-never-resolves.invalid/"


def wait_for(deadline: int, label: str) -> None:
    remaining = deadline - int(time.time()) + MARGIN
    if remaining > 0:
        print(f"    waiting {remaining}s for {label}...", flush=True)
        time.sleep(remaining)


def cool_down(label: str) -> None:
    """Wait out the contract's per-record review cooldown.

    The view does not publish `last_round_at`, and a test that has just run a
    round knows exactly when it did, so it waits the cooldown out itself instead
    of reading a field that was never exposed.
    """
    print(f"    waiting {COOLDOWN + MARGIN}s for {label}...", flush=True)
    time.sleep(COOLDOWN + MARGIN)


class Probe:
    def __init__(self, c, buyer, seller, third):
        self.c, self.buyer, self.seller, self.third = c, buyer, seller, third
        self.addr = c.address
        self.client = get_gl_client()
        # every read costs a request against a 30/minute budget, so a record
        # read after a step is cached until that record is written again
        self._cache: dict[int, dict] = {}

    def att(self, aid):
        if aid not in self._cache:
            self._cache[aid] = self.c.get_attestation(args=[aid]).call()
        return self._cache[aid]

    def forget(self, aid):
        self._cache.pop(aid, None)

    def stats(self):
        return self.c.get_stats(args=[]).call()

    # ---- writes: send once, then poll --------------------------------
    def _wait(self, tx_hash: str):
        """Poll a receipt without ever re-sending the transaction."""
        last = None
        for attempt in range(6):
            try:
                return self.client.wait_for_transaction_receipt(
                    transaction_hash=tx_hash,
                    status=TransactionStatus.ACCEPTED,
                    interval=8000,
                    retries=20,
                )
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e)
                rate_limited = "rate limit" in msg.lower() or "-32029" in msg
                transient = rate_limited or any(
                    k in msg for k in ("invalid JSON", "Expecting value", "timed out", "timeout", "Failed to fetch")
                )
                if not transient or attempt == 5:
                    raise
                wait = RATE_LIMIT_PAUSE if rate_limited else 10
                print(f"    [wait] {tx_hash[:12]} attempt {attempt + 1} retrying in {wait}s: {msg[:90]}", flush=True)
                time.sleep(wait)
        raise last if last else RuntimeError("unreachable")

    def _write(self, method: str, args: list, who, value: int = 0):
        tx_hash = _retry(
            lambda: self.client.write_contract(
                address=self.addr, function_name=method, account=who, value=value, args=args
            ),
            what=f"send {method}",
        )
        return self._wait(tx_hash)

    # ---- the functions ------------------------------------------------
    def request(self, url, claim, evidence="text", purpose="live function test", who=None, fee=FEE):
        who = who or self.buyer
        r = self._write("request_attestation", [url, claim, purpose, evidence], who, fee)
        assert tx_execution_succeeded(r), "request failed"
        return int(self.stats()["attestations"])

    def attest(self, aid, who=None):
        who = who or self.seller
        r = self._write("attest", [aid], who)
        assert tx_execution_succeeded(r), "attest failed"
        self.forget(aid)
        return self.att(aid)

    def challenge(self, aid, grounds="the verdict is wrong", who=None, bond=None):
        who = who or self.third
        if bond is None:
            bond = int(self.att(aid)["challenge_bond"])
        r = self._write("challenge", [aid, grounds], who, bond)
        assert tx_execution_succeeded(r), "challenge failed"
        self.forget(aid)

    def re_review(self, aid, who=None):
        who = who or self.buyer
        r = self._write("re_review", [aid], who)
        assert tx_execution_succeeded(r), "re_review failed"
        self.forget(aid)
        return self.att(aid)

    def claim_reward(self, aid, who=None):
        who = who or self.buyer
        r = self._write("claim_reward", [aid], who)
        assert tx_execution_succeeded(r), "claim_reward failed"
        self.forget(aid)
        return r

    def refund_stale(self, aid, who=None):
        who = who or self.third
        r = self._write("refund_stale", [aid], who)
        assert tx_execution_succeeded(r), "refund_stale failed"
        self.forget(aid)
        return r

    def finalize_challenge(self, aid, who=None):
        who = who or self.third
        r = self._write("finalize_challenge", [aid], who)
        assert tx_execution_succeeded(r), "finalize_challenge failed"
        self.forget(aid)
        return r

    def expect_revert(self, method, args, who, needle, what, value=0):
        raw = ""
        failed = False
        try:
            receipt = self._write(method, args, who, value)
            raw = json.dumps(receipt, default=str)
            failed = not tx_execution_succeeded(receipt)
        except Exception as e:  # noqa: BLE001 - a revert can surface either way
            raw = str(e)
            failed = True
        ok = failed and needle.lower() in raw.lower()
        detail = "" if ok else ("did not revert" if not failed else f"wrong reason: {raw[-240:]}")
        return record(what, ok, detail)


def test_live_functions():
    build_probe()
    accounts = get_accounts()
    buyer, seller, third = accounts[0], accounts[1], accounts[2]
    c = get_contract_factory("VisualProofFast").deploy(account=buyer)
    print(f"\nprobe deployed at {c.address}", flush=True)
    p = Probe(c, buyer, seller, third)

    try:
        # ======================= request_attestation =======================
        print("\n-- request_attestation --", flush=True)
        a1 = p.request(VISUAL_URL, VISUAL_CLAIM, "visual", "reward path")
        d = p.att(a1)
        record(
            "request stores the claim, the mode, the fee and the bond",
            d["status"] == "REQUESTED"
            and d["claim"] == VISUAL_CLAIM
            and d["evidence"] == "visual"
            and int(d["fee"]) == FEE
            and int(d["challenge_bond"]) == FEE
            and not d["has_verifier"],
            f"got {d['status']}/{d['evidence']}",
        )
        st = p.stats()
        record("get_stats counts the request and holds the fee", int(st["attestations"]) == 1 and int(st["held"]) == FEE)
        listed = c.list_attestations(args=[0, 50, False]).call()
        record("list_attestations returns it, newest first", len(listed) == 1 and int(listed[0]["id"]) == a1)
        record("a fresh record reports no verifier and no verdict", not d["has_verifier"] and d["verdict"] == "")

        p.expect_revert(
            "request_attestation",
            [VISUAL_URL, VISUAL_CLAIM, "x", "visual"],
            buyer,
            "fee is below the minimum",
            "request reverts below the minimum fee",
            value=FEE - 1,
        )
        p.expect_revert(
            "request_attestation",
            [VISUAL_URL, "   ", "x", "visual"],
            buyer,
            "claim",
            "request reverts on a blank claim",
            value=FEE,
        )
        p.expect_revert(
            "request_attestation",
            [VISUAL_URL, VISUAL_CLAIM, "x", "pixels"],
            buyer,
            "evidence must be",
            "request reverts on an unknown evidence mode",
            value=FEE,
        )
        p.expect_revert(
            "request_attestation",
            ["http://127.1/work", VISUAL_CLAIM, "x", "text"],
            buyer,
            "publicly renderable",
            "request reverts on a numeric loopback spelling",
            value=FEE,
        )

        # ======================= attest, visual ============================
        print("\n-- attest (visual, live vision consensus) --", flush=True)
        d = p.attest(a1)
        need(
            d["status"] == "ATTESTED" and d["verdict"] in ("CONFIRMED", "REFUTED"),
            f"the visual attestation did not reach a verdict on the network: {d['status']}/{d['verdict']}",
        )
        record("attest reaches a verdict on a real screenshot", True)
        record("attest records the verifier who ran it", bool(d["has_verifier"]))
        record("the reward is held, not paid, while the window is open", int(p.stats()["rewarded"]) == 0)
        print(f"    verdict={d['verdict']} confidence={d['confidence']}", flush=True)
        print(f"    evidence: {str(d['reasoning'])[:170]}", flush=True)
        p.expect_revert("attest", [a1], seller, "not open for attestation", "attest reverts on a standing verdict")
        p.expect_revert("attest", [999], seller, "attestation not found", "attest reverts on a missing id")

        # ======================= claim_reward, too early ===================
        print("\n-- claim_reward --", flush=True)
        p.expect_revert(
            "claim_reward", [a1], buyer, "challenge window still open", "claim_reward reverts while the window is open"
        )

        # ======================= challenge guards ==========================
        print("\n-- challenge --", flush=True)
        p.expect_revert(
            "challenge",
            [a1, "wrong bond"],
            third,
            "exactly this attestation's challenge bond",
            "challenge reverts on the wrong bond",
            value=FEE - 1,
        )
        p.expect_revert(
            "re_review", [a1], third, "no challenge is pending", "re_review reverts with no challenge pending"
        )

        # ======================= claim_reward, after =======================
        wait_for(int(p.att(a1)["verdict_at"]) + WINDOW, "the challenge window to close")
        p.claim_reward(a1)
        d = p.att(a1)
        st = p.stats()
        record("claim_reward pays the verifier once the window closes", d["status"] == "REWARDED" and int(st["rewarded"]) == FEE)
        record("claim_reward moves the fee out of the held bucket", int(st["held"]) == 0)

        # ======================= challenge upheld ==========================
        print("\n-- challenge + re_review that agrees (UPHELD) --", flush=True)
        url_b = new_webhook()
        write_page(url_b, f"marker: {MARKER}")
        b = p.request(url_b, TEXT_CLAIM, "text", "upheld path")
        db = p.attest(b)
        need(db["verdict"] == "CONFIRMED", f"the text attestation expected CONFIRMED, got {db['verdict']}")
        record("text mode reaches a verdict", True)
        p.challenge(b, "the marker may have been removed")
        record("challenge stakes the bond and flips the state", p.att(b)["status"] == "CHALLENGED")
        record("the staked bond is held by the contract", int(p.stats()["bonds_held"]) == FEE)
        cool_down("the review cooldown")
        db = p.re_review(b)
        st = p.stats()
        need(db["status"] == "UPHELD", f"expected UPHELD, got {db['status']}")
        record("re_review that agrees upholds the record", True)
        record("the forfeited bond is released as a payout", int(st["bond_payouts"]) == FEE and int(st["bonds_held"]) == 0)

        # ======================= challenge overturned ======================
        print("\n-- challenge + re_review that flips (OVERTURNED) --", flush=True)
        url_c = new_webhook()
        write_page(url_c, f"marker: {MARKER}")
        cc = p.request(url_c, TEXT_CLAIM, "text", "overturn path")
        p.attest(cc)
        p.challenge(cc, "the page has changed since the verdict")
        write_page(url_c, "the marker has been removed from this page")
        refunded_before = int(p.stats()["refunded"])
        cool_down("the review cooldown")
        d = p.re_review(cc)
        st = p.stats()
        need(d["status"] == "OVERTURNED", f"expected OVERTURNED, got {d['status']}")
        record("re_review that flips corrects the record", d["verdict"] == "REFUTED")
        record("the corrected record refunds the fee", int(st["refunded"]) == refunded_before + FEE)

        # ======================= force refund ==============================
        print("\n-- attest on a page that never renders (force refund) --", flush=True)
        e = p.request(DEAD_URL, "The page shows anything at all.", "text", "refund path")
        for _ in range(2):
            p.attest(e)
            cool_down("the review cooldown")
        de = p.attest(e)
        record(
            "three unrenderable rounds refund the fee",
            de["status"] == "REFUNDED" and int(p.stats()["void_rounds"]) >= 3,
            f"got {de['status']}",
        )

        # ======================= refund_stale ==============================
        print("\n-- refund_stale --", flush=True)
        f = p.request(VISUAL_URL, VISUAL_CLAIM, "visual", "stale path")
        p.expect_revert(
            "refund_stale", [f], third, "not closed yet", "refund_stale reverts before its window closes"
        )
        wait_for(int(p.att(f)["requested_at"]) + WINDOW + SLACK, "the attestation window to close")
        p.refund_stale(f)
        record("refund_stale returns a fee nobody attested", p.att(f)["status"] == "REFUNDED")

        # ======================= finalize_challenge ========================
        print("\n-- finalize_challenge --", flush=True)
        g = p.request(VISUAL_URL, VISUAL_CLAIM, "visual", "finalize path")
        p.attest(g)
        p.challenge(g, "left unreviewed on purpose")
        p.expect_revert(
            "finalize_challenge", [g], third, "still open", "finalize_challenge reverts while the window is open"
        )
        wait_for(int(p.att(g)["challenged_at"]) + WINDOW, "the re-review window to pass")
        p.finalize_challenge(g)
        dg = p.att(g)
        need(dg["status"] == "ATTESTED" and dg["challenge_voided"], f"expected a voided challenge, got {dg['status']}")
        record("finalize_challenge returns the bond and keeps the record", True)
        p.claim_reward(g)
        record("a voided challenge still lets the verifier be paid", p.att(g)["status"] == "REWARDED")

        # ======================= state machine guards ======================
        print("\n-- guards and state machine --", flush=True)
        p.expect_revert(
            "challenge",
            [g, "second try"],
            third,
            "only a standing verdict",
            "a resolved attestation cannot be challenged again",
            value=FEE,
        )
        p.expect_revert(
            "attest", [a1], buyer, "not open for attestation", "a rewarded attestation accepts no new round"
        )
        p.expect_revert("claim_reward", [b], buyer, "nothing to reward", "claim_reward reverts on a resolved record")
        p.expect_revert(
            "refund_stale", [b], third, "only an unattested request", "refund_stale reverts on a record with a verdict"
        )
        p.expect_revert(
            "finalize_challenge", [b], third, "no challenge is pending", "finalize_challenge reverts with no challenge"
        )
        st = p.stats()
        record(
            "every challenge bond has been resolved by this point",
            int(st["bonds_held"]) == 0,
            f"bonds_held={int(st['bonds_held'])}",
        )
        record(
            "get_stats reports one overturned challenge",
            int(st["overturned"]) == 1 and int(st["challenged"]) >= 3,
            f"overturned={st['overturned']} challenged={st['challenged']}",
        )
        try:
            c.list_attestations(args=[0, 51, False]).call()
            record("list_attestations refuses bad pagination", False, "it returned instead of reverting")
        except Exception as e:  # noqa: BLE001
            # a reverting view surfaces as a bare "execution failed" over the RPC,
            # so the reason string is asserted in the direct tests instead
            msg = str(e).lower()
            record(
                "list_attestations refuses bad pagination",
                "execution failed" in msg or "bad pagination" in msg,
                str(e)[:120],
            )

        # ======================= states for the frontend ===================
        print("\n-- states left pending for the frontend sweep --", flush=True)
        h1 = p.request(VISUAL_URL, VISUAL_CLAIM, "visual", "frontend: expired request")
        h2 = p.request(VISUAL_URL, VISUAL_CLAIM, "visual", "frontend: expired window")
        p.attest(h2)
        h3 = p.request(VISUAL_URL, VISUAL_CLAIM, "visual", "frontend: expired challenge")
        p.attest(h3)
        p.challenge(h3, "frontend sweep")
        deadlines = [
            int(p.att(h1)["requested_at"]) + WINDOW + SLACK,
            int(p.att(h2)["verdict_at"]) + WINDOW,
            int(p.att(h3)["challenged_at"]) + WINDOW,
        ]
        wait_for(max(deadlines), "all three windows to close together")
        need(p.att(h1)["status"] == "REQUESTED", f"h1 should still be REQUESTED, got {p.att(h1)['status']}")
        need(p.att(h2)["status"] == "ATTESTED", f"h2 should still be ATTESTED, got {p.att(h2)['status']}")
        need(p.att(h3)["status"] == "CHALLENGED", f"h3 should still be CHALLENGED, got {p.att(h3)['status']}")
        record("a REQUESTED record past its window waits for a refund", True)
        record("an ATTESTED record past its window waits for its reward", True)
        record("a CHALLENGED record past its window waits to be finalized", True)

        # ======================= accounting ================================
        st = p.stats()
        print(
            f"\nstats: attestations={st['attestations']} attested={st['attested']} confirmed={st['confirmed']} "
            f"refuted={st['refuted']} challenged={st['challenged']} overturned={st['overturned']} "
            f"void_rounds={st['void_rounds']}",
            flush=True,
        )
        print(
            f"money: held={int(st['held']) / GEN} bonds_held={int(st['bonds_held']) / GEN} "
            f"rewarded={int(st['rewarded']) / GEN} refunded={int(st['refunded']) / GEN} "
            f"bond_payouts={int(st['bond_payouts']) / GEN}",
            flush=True,
        )
        permanent = int(st["rewarded"]) + int(st["refunded"])
        record(
            "every fee is either still held, or paid/refunded and accounted for",
            int(st["attestations"]) * FEE == int(st["held"]) + permanent,
            f"{int(st['attestations']) * FEE} != {int(st['held'])} + {permanent}",
        )
        print(f"\nLIVE_PROBE_ADDRESS={c.address}", flush=True)
        print(f"FRONTEND_STATES={h1},{h2},{h3}", flush=True)
    finally:
        if PROBE.exists():
            PROBE.unlink()
            print("\n(probe contract source removed)", flush=True)

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n===== {len(RESULTS) - len(failed)}/{len(RESULTS)} live checks passed =====", flush=True)
    for name, _, detail in failed:
        print(f"  FAILED: {name}  {detail}", flush=True)
    assert not failed, f"{len(failed)} live checks failed"


if __name__ == "__main__":
    test_live_functions()
