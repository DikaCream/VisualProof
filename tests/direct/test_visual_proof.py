"""VisualProof direct-mode tests: the attestation machine, exhaustively.

Everything here runs in a local VM with mocked web and vision responses, so
every guard is covered deterministically. The real consensus path (validators
rendering a page and reading it with a vision model) is covered by the
StudioNet smoke test and the end-to-end run, because only a live network can
disagree with itself.

Clock discipline: assigning ``vm.sender`` or ``vm.value`` rebuilds the message
context and restores the block time to the wall clock, so the helpers below
set sender, value and time in that order, immediately before the call.
"""

import json
import time

import pytest

from tests.direct.conftest import set_time, iso

GEN = 10**18
FEE = GEN // 100          # 0.01 GEN
BIG_FEE = GEN // 10       # 0.1 GEN
BOND = GEN // 100         # 0.01 GEN, the floor
T0 = 1790000000           # an arbitrary, fixed block time
DAY = 24 * 3600
WINDOW = DAY              # CHALLENGE_WINDOW
ATTEST_WINDOW = 3 * DAY
SLACK = 3600
COOLDOWN = 60

TARGET = "https://example.com/attested-page"
CLAIM = "The page shows the phrase 'delivery accepted' as a visible heading."
PURPOSE = "Releasing a milestone payment to a contractor."
PAGE_BODY = "delivery accepted - the work is complete"


def _reset():
    import genlayer.gl.genvm_contracts as gvc

    gvc.__known_contract__ = None  # the direct loader does not reset this


@pytest.fixture()
def vp(direct_vm, direct_deploy):
    c = direct_deploy("contracts/visual_proof.py")
    yield c
    _reset()


# ----------------------------------------------------------------- helpers
def call(vm, fn, sender, value=0, at=None):
    """Assign sender and value, then the block time, then call.

    That order matters: the context assignments restore the wall clock, so the
    time has to be set last to survive into the call.
    """
    vm.sender = sender
    vm.value = value
    if at is not None:
        set_time(iso(at))
    out = fn()
    vm.value = 0
    return out


def request(vp, vm, requester, fee=FEE, url=TARGET, claim=CLAIM, purpose=PURPOSE, at=T0, evidence="text"):
    return int(call(vm, lambda: vp.request_attestation(url, claim, purpose, evidence), requester, fee, at))


def mock_verdict(vm, verdict="CONFIRMED", confidence="high", body=PAGE_BODY):
    """Mocks are first-match-wins, so a verdict flip needs the old ones gone."""
    vm.clear_mocks()
    vm.mock_web(r"https://example\.com/attested-page", {"status": 200, "body": body})
    vm.mock_llm(
        r".*verifier for a public attestation.*",
        json.dumps(
            {
                "verdict": verdict,
                "evidence": "The heading reads 'delivery accepted'.",
                "confidence": confidence,
            }
        ),
    )


def mock_garbage(vm):
    vm.clear_mocks()
    vm.mock_web(r"https://example\.com/attested-page", {"status": 200, "body": PAGE_BODY})
    vm.mock_llm(r".*verifier for a public attestation.*", '{"note": "no verdict here"}')


def attest(vp, vm, who, aid, at=T0 + COOLDOWN + 1):
    return call(vm, lambda: vp.attest(aid), who, 0, at)


# ---------------------------------------------------------------- request
def test_request_attestation(vp, direct_vm, direct_alice):
    aid = request(vp, direct_vm, direct_alice)
    a = vp.get_attestation(aid)
    assert a["status"] == "REQUESTED"
    assert not a["has_verifier"]
    assert int(a["fee"]) == FEE
    assert int(a["challenge_bond"]) == FEE  # fee above the floor sets the bond
    assert a["claim"] == CLAIM
    assert a["target_url"] == TARGET
    stats = vp.get_stats()
    assert int(stats["attestations"]) == 1
    assert int(stats["held"]) == FEE  # the fee is held, not yet earned


def test_request_bond_floor_when_fee_is_small(vp, direct_vm, direct_alice):
    """A fee of exactly the minimum still carries a challengeable bond."""
    aid = request(vp, direct_vm, direct_alice, fee=GEN // 100)
    assert int(vp.get_attestation(aid)["challenge_bond"]) == BOND


def test_request_bond_tracks_a_larger_fee(vp, direct_vm, direct_alice):
    aid = request(vp, direct_vm, direct_alice, fee=BIG_FEE)
    assert int(vp.get_attestation(aid)["challenge_bond"]) == BIG_FEE


def test_request_reverts_below_min_fee(vp, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    direct_vm.value = GEN // 100 - 1
    with pytest.raises(Exception, match="fee is below the minimum"):
        vp.request_attestation(TARGET, CLAIM, PURPOSE, "text")
    direct_vm.value = 0


def test_request_reverts_without_fee(vp, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="fee is below the minimum"):
        vp.request_attestation(TARGET, CLAIM, PURPOSE, "text")


@pytest.mark.parametrize("claim", ["", "   ", "x" * 401])
def test_request_reverts_bad_claim(vp, direct_vm, direct_alice, claim):
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    with pytest.raises(Exception, match="claim"):
        vp.request_attestation(TARGET, claim, PURPOSE, "text")
    direct_vm.value = 0


def test_request_reverts_oversized_purpose(vp, direct_vm, direct_alice):
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    with pytest.raises(Exception, match="purpose"):
        vp.request_attestation(TARGET, CLAIM, "p" * 301, "text")
    direct_vm.value = 0


@pytest.mark.parametrize("url", ["ftp://x.example/a", "not a url", "", "https://" + "a" * 500])
def test_request_reverts_bad_url(vp, direct_vm, direct_alice, url):
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    with pytest.raises(Exception, match="url"):
        vp.request_attestation(url, CLAIM, PURPOSE, "text")
    direct_vm.value = 0


@pytest.mark.parametrize(
    "url",
    [
        # plain private and reserved targets
        "http://localhost:8080/work",
        "http://localhost.",
        "http://127.0.0.1/work",
        "http://10.0.0.5/work",
        "http://172.16.0.9/work",
        "http://172.31.255.1/work",
        "http://192.168.1.1/work",
        "http://169.254.10.9/work",
        "http://100.64.0.1/work",
        "http://work.internal/report",
        "http://page.local/report",
        "http://[::1]/work",
        "http://0.0.0.0/work",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://metadata.google.internal./x",
        # the spelling games that walk past a naive host check
        "http://127.1/work",
        "http://2130706433/work",
        "http://0x7f000001/work",
        "http://0177.0.0.1/work",
        "http://8.8.8.8/work",
        "http://localhost:80@127.0.0.1/work",
        "http://example.com:8080@127.1/work",
        # wildcard-DNS services: a hostname that resolves wherever you like
        "http://127.0.0.1.nip.io/work",
        "http://169.254.169.254.nip.io/work",
        "http://box.lvh.me/work",
        "http://thing.sslip.io/work",
    ],
)
def test_request_reverts_unrenderable_url(vp, direct_vm, direct_alice, url):
    """A page only the requester can reach can never be judged: rejecting it at
    request time spares everyone three rounds of unrenderable verdicts."""
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    with pytest.raises(Exception, match="publicly renderable"):
        vp.request_attestation(url, CLAIM, PURPOSE, "text")
    direct_vm.value = 0
    assert int(vp.get_stats()["attestations"]) == 0  # nothing was created


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/work",
        "https://raw.githubusercontent.com/owner/repo/main/README.md",
        "http://example.com:8443/" + "deep/path",
        "https://0xproject.com/",  # a real name that merely starts with 0x
        "https://sub.domain.example.co.uk/x",
    ],
)
def test_request_accepts_public_urls(vp, direct_vm, direct_alice, url):
    aid = request(vp, direct_vm, direct_alice, url=url)
    assert vp.get_attestation(aid)["status"] == "REQUESTED"


def test_request_records_the_evidence_mode(vp, direct_vm, direct_alice):
    vid = request(vp, direct_vm, direct_alice, evidence="visual")
    tid = request(vp, direct_vm, direct_alice, evidence="text")
    assert vp.get_attestation(vid)["evidence"] == "visual"
    assert vp.get_attestation(tid)["evidence"] == "text"


@pytest.mark.parametrize("mode", ["pixels", "", "vision", "screenshot", "VISUALISH"])
def test_request_reverts_bad_evidence_mode(vp, direct_vm, direct_alice, mode):
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    with pytest.raises(Exception, match="evidence must be"):
        vp.request_attestation(TARGET, CLAIM, PURPOSE, mode)
    direct_vm.value = 0
    assert int(vp.get_stats()["attestations"]) == 0


def test_visual_mode_burns_a_round_on_an_empty_image(vp, direct_vm, direct_alice, direct_bob):
    """The direct VM cannot produce a real screenshot: it hands back an empty
    image, and the contract must treat that as unrenderable rather than let a
    model judge nothing at all. The live vision path is covered by the
    StudioNet smoke test and the end-to-end run, because only a real renderer
    can produce pixels."""
    aid = request(vp, direct_vm, direct_alice, evidence="visual")
    mock_verdict(direct_vm)  # the mocks are in place; the image is still empty
    assert attest(vp, direct_vm, direct_bob, aid) == "UNRENDERABLE"
    a = vp.get_attestation(aid)
    assert a["status"] == "REQUESTED"
    assert int(a["rounds"]) == 1


def test_text_mode_treats_a_blank_page_as_unrenderable(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice, evidence="text")
    direct_vm.clear_mocks()
    direct_vm.mock_web(r"https://example\.com/attested-page", {"status": 200, "body": "   \n  "})
    assert attest(vp, direct_vm, direct_bob, aid) == "UNRENDERABLE"


# ----------------------------------------------------------------- attest
def test_attest_confirms_and_holds_the_reward(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    mock_verdict(direct_vm, "CONFIRMED")
    assert attest(vp, direct_vm, direct_bob, aid) == "CONFIRMED"
    a = vp.get_attestation(aid)
    assert a["status"] == "ATTESTED"
    assert a["verdict"] == "CONFIRMED"
    assert a["has_verifier"]
    assert str(a["verifier"]).lower() == str(direct_bob).lower()
    stats = vp.get_stats()
    assert int(stats["attested"]) == 1
    assert int(stats["confirmed"]) == 1
    # the reward is still held: the challenge window has not closed
    assert int(stats["held"]) == FEE
    assert int(stats["rewarded"]) == 0


def test_attest_refutes(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    mock_verdict(direct_vm, "REFUTED")
    assert attest(vp, direct_vm, direct_bob, aid) == "REFUTED"
    a = vp.get_attestation(aid)
    assert a["status"] == "ATTESTED"
    assert a["verdict"] == "REFUTED"
    assert int(vp.get_stats()["refuted"]) == 1


def test_attest_is_permissionless(vp, direct_vm, direct_alice, direct_charlie):
    """Anyone may run the judgement; the runner becomes the verifier who gets
    paid, so verification is a job anyone can take."""
    aid = request(vp, direct_vm, direct_alice)
    mock_verdict(direct_vm)
    assert attest(vp, direct_vm, direct_charlie, aid) == "CONFIRMED"
    assert vp.get_attestation(aid)["has_verifier"]


def test_low_confidence_never_settles_anyone(vp, direct_vm, direct_alice, direct_bob):
    """A verdict the model itself is unsure about burns a round instead of
    settling a claim on a guess."""
    aid = request(vp, direct_vm, direct_alice)
    mock_verdict(direct_vm, "CONFIRMED", confidence="low")
    assert attest(vp, direct_vm, direct_bob, aid) == "LOW_CONFIDENCE"
    a = vp.get_attestation(aid)
    assert a["status"] == "REQUESTED"
    assert int(a["rounds"]) == 1
    assert not a["has_verifier"]
    assert int(vp.get_stats()["void_rounds"]) == 1


def test_garbled_verdict_burns_a_round(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    mock_garbage(direct_vm)
    assert attest(vp, direct_vm, direct_bob, aid) == "INVALID"
    assert vp.get_attestation(aid)["status"] == "REQUESTED"


def test_unrenderable_page_refunds_after_max_rounds(vp, direct_vm, direct_alice, direct_bob):
    """No mock at all: the render fails, so three rounds burn and the fee goes
    back instead of the request holding money forever."""
    aid = request(vp, direct_vm, direct_alice)
    for i in range(2):
        assert attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * (i + 2)) == "UNRENDERABLE"
    assert attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * 4) == "REFUNDED"
    a = vp.get_attestation(aid)
    assert a["status"] == "REFUNDED"
    stats = vp.get_stats()
    assert int(stats["held"]) == 0
    assert int(stats["refunded"]) == FEE
    assert int(stats["rewarded"]) == 0
    with pytest.raises(Exception, match="not open for attestation"):
        attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * 5)


def test_render_can_recover_before_the_rounds_run_out(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    assert attest(vp, direct_vm, direct_bob, aid) == "UNRENDERABLE"
    mock_verdict(direct_vm)
    assert attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * 3) == "CONFIRMED"
    assert int(vp.get_stats()["confirmed"]) == 1


def test_attest_cooldown(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN + 1)
    direct_vm.sender = direct_bob
    set_time(iso(T0 + COOLDOWN + 30))
    with pytest.raises(Exception, match="cooldown"):
        vp.attest(aid)


def test_attest_reverts_on_a_settled_request(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    mock_verdict(direct_vm)
    attest(vp, direct_vm, direct_bob, aid)
    direct_vm.sender = direct_bob
    with pytest.raises(Exception, match="not open for attestation"):
        vp.attest(aid)


def test_attest_reverts_for_a_missing_id(vp, direct_vm, direct_bob):
    direct_vm.sender = direct_bob
    with pytest.raises(Exception, match="attestation not found"):
        vp.attest(999)


# ---------------------------------------------------------------- reward
def _stand(vp, vm, requester, verifier, verdict="CONFIRMED"):
    aid = request(vp, vm, requester)
    mock_verdict(vm, verdict)
    attest(vp, vm, verifier, aid)
    return aid


def test_claim_reward_after_the_window(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(
        direct_vm,
        lambda: vp.claim_reward(aid),
        direct_bob,
        0,
        T0 + COOLDOWN + WINDOW + 10,
    )
    a = vp.get_attestation(aid)
    assert a["status"] == "REWARDED"
    stats = vp.get_stats()
    assert int(stats["held"]) == 0
    assert int(stats["rewarded"]) == FEE
    assert int(stats["refunded"]) == 0


def test_claim_reward_reverts_while_the_window_is_open(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    set_time(iso(T0 + COOLDOWN + WINDOW - 60))
    with pytest.raises(Exception, match="challenge window still open"):
        vp.claim_reward(aid)


def test_claim_reward_reverts_on_a_request_with_no_verdict(vp, direct_vm, direct_alice):
    aid = request(vp, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="nothing to reward"):
        vp.claim_reward(aid)


# ------------------------------------------------------------- challenge
def test_challenge_stakes_the_bond(vp, direct_vm, direct_alice, direct_bob, direct_charlie):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(
        direct_vm,
        lambda: vp.challenge(aid, "The banner is not in the rendered page."),
        direct_charlie,
        FEE,
        T0 + COOLDOWN + 60,
    )
    a = vp.get_attestation(aid)
    assert a["status"] == "CHALLENGED"
    assert a["has_challenger"]
    assert int(a["challenges"]) == 1
    stats = vp.get_stats()
    assert int(stats["bonds_held"]) == FEE
    assert int(stats["challenged"]) == 1
    assert int(stats["held"]) == FEE  # the reward is still held too


def test_challenge_reverts_without_a_standing_verdict(vp, direct_vm, direct_alice):
    aid = request(vp, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    with pytest.raises(Exception, match="only a standing verdict"):
        vp.challenge(aid, "grounds")
    direct_vm.value = 0


def test_challenge_reverts_with_the_wrong_bond(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob, verdict="REFUTED")
    direct_vm.sender = direct_alice
    direct_vm.value = FEE - 1
    set_time(iso(T0 + COOLDOWN + 60))
    with pytest.raises(Exception, match="exactly this attestation's challenge bond"):
        vp.challenge(aid, "grounds")
    direct_vm.value = 0


def test_challenge_reverts_after_the_window(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    set_time(iso(T0 + COOLDOWN + WINDOW + 60))
    with pytest.raises(Exception, match="challenge window closed"):
        vp.challenge(aid, "grounds")
    direct_vm.value = 0


def test_challenge_is_single_shot(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(direct_vm, lambda: vp.challenge(aid, "first"), direct_alice, FEE, T0 + COOLDOWN + 60)
    call(direct_vm, lambda: vp.re_review(aid), direct_bob, 0, T0 + COOLDOWN * 3)
    # the re-review upheld it; a second challenge is refused for good
    assert vp.get_attestation(aid)["status"] == "UPHELD"
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    with pytest.raises(Exception, match="only a standing verdict"):
        vp.challenge(aid, "again")
    direct_vm.value = 0


def test_challenge_cannot_be_restaked_after_it_is_spent(vp, direct_vm, direct_alice, direct_bob, direct_charlie):
    """A voided challenge is spent for good: the window closing must not hand
    anyone a second bite at the same standing verdict."""
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(direct_vm, lambda: vp.challenge(aid, "grounds"), direct_charlie, FEE, T0 + COOLDOWN + 60)
    call(direct_vm, lambda: vp.finalize_challenge(aid), direct_charlie, 0, T0 + COOLDOWN + WINDOW + 120)
    assert vp.get_attestation(aid)["status"] == "ATTESTED"
    assert vp.get_attestation(aid)["challenge_voided"]
    direct_vm.sender = direct_charlie
    direct_vm.value = FEE
    set_time(iso(T0 + COOLDOWN + WINDOW + 200))
    with pytest.raises(Exception, match="already challenged"):
        vp.challenge(aid, "again")
    direct_vm.value = 0


def test_challenge_reverts_for_oversized_grounds(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    direct_vm.value = FEE
    set_time(iso(T0 + COOLDOWN + 60))
    with pytest.raises(Exception, match="grounds"):
        vp.challenge(aid, "g" * 501)
    direct_vm.value = 0


# -------------------------------------------------------------- re-review
def test_re_review_upholds_and_the_bond_pays_the_verifier(vp, direct_vm, direct_alice, direct_bob, direct_charlie):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob, verdict="CONFIRMED")
    call(direct_vm, lambda: vp.challenge(aid, "the banner is not there"), direct_charlie, FEE, T0 + COOLDOWN + 60)
    mock_verdict(direct_vm, "CONFIRMED")  # the re-review agrees
    assert call(direct_vm, lambda: vp.re_review(aid), direct_charlie, 0, T0 + COOLDOWN * 3) == "UPHELD"
    a = vp.get_attestation(aid)
    assert a["status"] == "UPHELD"
    stats = vp.get_stats()
    assert int(stats["bonds_held"]) == 0
    assert int(stats["bond_payouts"]) == FEE
    assert int(stats["rewarded"]) == FEE
    # the verifier is paid the reward plus the forfeited bond: the two buckets
    # are tracked separately and sum to what left the contract
    assert int(stats["rewarded"]) + int(stats["bond_payouts"]) == FEE * 2
    assert int(stats["held"]) == 0
    assert int(stats["overturned"]) == 0


def test_re_review_overturns_and_corrects_the_record(vp, direct_vm, direct_alice, direct_bob, direct_charlie):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob, verdict="CONFIRMED")
    call(direct_vm, lambda: vp.challenge(aid, "the banner is not there"), direct_charlie, FEE, T0 + COOLDOWN + 60)
    mock_verdict(direct_vm, "REFUTED")  # the re-review flips it
    assert call(direct_vm, lambda: vp.re_review(aid), direct_charlie, 0, T0 + COOLDOWN * 3) == "OVERTURNED"
    a = vp.get_attestation(aid)
    assert a["status"] == "OVERTURNED"
    assert a["verdict"] == "REFUTED"
    stats = vp.get_stats()
    assert int(stats["held"]) == 0
    assert int(stats["refunded"]) == FEE        # the requester paid for a wrong answer
    assert int(stats["bonds_held"]) == 0
    assert int(stats["bond_payouts"]) == FEE    # the challenger keeps their stake
    assert int(stats["rewarded"]) == 0
    assert int(stats["overturned"]) == 1
    assert int(stats["confirmed"]) == 0
    assert int(stats["refuted"]) == 1


def test_void_challenge_returns_the_bond_and_frees_the_reward(vp, direct_vm, direct_alice, direct_bob, direct_charlie):
    """A challenge that never reaches a verdict must not punish the challenger
    nor freeze the verifier's fee."""
    aid = _stand(vp, direct_vm, direct_alice, direct_bob, verdict="REFUTED")
    call(direct_vm, lambda: vp.challenge(aid, "grounds"), direct_charlie, FEE, T0 + COOLDOWN + 60)
    direct_vm.clear_mocks()  # the page becomes unrenderable for the re-review
    # challenge has its own MAX_CHALLENGE_ROUNDS=3 budget, so it takes 3 unrenderable rounds to void
    assert call(direct_vm, lambda: vp.re_review(aid), direct_charlie, 0, T0 + COOLDOWN * 3) == "UNRENDERABLE"
    assert call(direct_vm, lambda: vp.re_review(aid), direct_charlie, 0, T0 + COOLDOWN * 5) == "UNRENDERABLE"
    assert call(direct_vm, lambda: vp.re_review(aid), direct_charlie, 0, T0 + COOLDOWN * 7) == "ATTESTED"
    a = vp.get_attestation(aid)
    assert a["status"] == "ATTESTED"
    assert a["challenge_voided"]
    assert a["verdict"] == "REFUTED"           # the standing record survives
    stats = vp.get_stats()
    assert int(stats["bonds_held"]) == 0
    assert int(stats["bond_payouts"]) == FEE   # returned, not forfeited
    assert int(stats["rewarded"]) == 0
    # and the verifier can now be paid despite the window not having expired
    call(direct_vm, lambda: vp.claim_reward(aid), direct_bob, 0, T0 + COOLDOWN * 9)
    assert int(vp.get_stats()["rewarded"]) == FEE


def test_finalize_challenge_after_the_window(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(direct_vm, lambda: vp.challenge(aid, "grounds"), direct_alice, FEE, T0 + COOLDOWN + 60)
    direct_vm.sender = direct_bob
    set_time(iso(T0 + COOLDOWN + 120))
    with pytest.raises(Exception, match="re-review window still open"):
        vp.finalize_challenge(aid)
    call(direct_vm, lambda: vp.finalize_challenge(aid), direct_bob, 0, T0 + COOLDOWN + WINDOW + 120)
    a = vp.get_attestation(aid)
    assert a["status"] == "ATTESTED"
    assert a["challenge_voided"]
    assert int(vp.get_stats()["bond_payouts"]) == FEE


def test_finalize_challenge_reverts_without_a_challenge(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    set_time(iso(T0 + COOLDOWN + WINDOW + 60))
    with pytest.raises(Exception, match="no challenge is pending"):
        vp.finalize_challenge(aid)


def test_re_review_reverts_without_a_challenge(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    set_time(iso(T0 + COOLDOWN * 3))
    with pytest.raises(Exception, match="no challenge is pending"):
        vp.re_review(aid)


def test_re_review_reverts_after_its_window(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(direct_vm, lambda: vp.challenge(aid, "grounds"), direct_alice, FEE, T0 + COOLDOWN + 60)
    direct_vm.sender = direct_bob
    set_time(iso(T0 + COOLDOWN + WINDOW + 120))
    with pytest.raises(Exception, match="re-review window closed"):
        vp.re_review(aid)


def test_challenge_restarts_the_review_clock(vp, direct_vm, direct_alice, direct_bob):
    """Staking late in the window still buys a full window for the re-review:
    the re-review below runs after the original window has already closed."""
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(direct_vm, lambda: vp.challenge(aid, "late"), direct_alice, FEE, T0 + COOLDOWN + WINDOW - 60)
    mock_verdict(direct_vm, "REFUTED")
    late_but_inside_the_new_window = T0 + COOLDOWN + WINDOW + 5000
    assert call(direct_vm, lambda: vp.re_review(aid), direct_bob, 0, late_but_inside_the_new_window) == "OVERTURNED"


# ------------------------------------------------------------ refunds
def test_refund_stale_returns_the_fee(vp, direct_vm, direct_alice, direct_charlie):
    aid = request(vp, direct_vm, direct_alice)
    direct_vm.sender = direct_charlie  # anyone may clean up
    set_time(iso(T0 + ATTEST_WINDOW + SLACK + 10))
    vp.refund_stale(aid)
    a = vp.get_attestation(aid)
    assert a["status"] == "REFUNDED"
    stats = vp.get_stats()
    assert int(stats["held"]) == 0
    assert int(stats["refunded"]) == FEE
    assert int(stats["void_rounds"]) == 0  # nobody even tried: no round burned


def test_refund_stale_reverts_early(vp, direct_vm, direct_alice, direct_charlie):
    aid = request(vp, direct_vm, direct_alice)
    direct_vm.sender = direct_charlie
    set_time(iso(T0 + ATTEST_WINDOW))
    with pytest.raises(Exception, match="not closed yet"):
        vp.refund_stale(aid)


def test_refund_stale_reverts_on_a_standing_verdict(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    set_time(iso(T0 + ATTEST_WINDOW + SLACK + 10))
    with pytest.raises(Exception, match="only an unattested request"):
        vp.refund_stale(aid)


# --------------------------------------------------------- state machine
def test_terminal_states_accept_nothing(vp, direct_vm, direct_alice, direct_bob):
    aid = _stand(vp, direct_vm, direct_alice, direct_bob)
    call(direct_vm, lambda: vp.claim_reward(aid), direct_bob, 0, T0 + COOLDOWN + WINDOW + 10)
    assert vp.get_attestation(aid)["status"] == "REWARDED"
    direct_vm.sender = direct_bob
    with pytest.raises(Exception, match="not open for attestation"):
        vp.attest(aid)
    with pytest.raises(Exception, match="only a standing verdict|already challenged|challenge window closed"):
        direct_vm.value = FEE
        vp.challenge(aid, "too late")
    direct_vm.value = 0
    with pytest.raises(Exception, match="nothing to reward"):
        vp.claim_reward(aid)
    with pytest.raises(Exception, match="only an unattested request"):
        vp.refund_stale(aid)
    with pytest.raises(Exception, match="no challenge is pending"):
        vp.finalize_challenge(aid)


def test_a_refunded_request_cannot_be_attested(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    for i in range(2):
        attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * (i + 2))
    assert attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * 4) == "REFUNDED"
    direct_vm.sender = direct_bob
    set_time(iso(T0 + COOLDOWN * 5))
    with pytest.raises(Exception, match="not open for attestation"):
        vp.attest(aid)


# ----------------------------------------------------------------- views
def test_list_attestations_pagination_and_mine(vp, direct_vm, direct_alice, direct_bob, direct_charlie):
    ids = []
    for who in (direct_alice, direct_bob, direct_charlie):
        ids.append(request(vp, direct_vm, who, at=T0 + len(ids)))
    page = vp.list_attestations(0, 2, False)
    assert len(page) == 2
    assert int(page[0]["id"]) == ids[2]  # newest first
    direct_vm.sender = direct_bob
    assert len(vp.list_attestations(0, 50, True)) == 1
    assert len(vp.list_attestations(1, 50, False)) == 2


def test_list_attestations_reverts_bad_pagination(vp, direct_vm, direct_alice):
    with pytest.raises(Exception, match="bad pagination"):
        vp.list_attestations(0, 51, False)


def test_get_attestation_missing(vp, direct_vm, direct_alice):
    with pytest.raises(Exception, match="attestation not found"):
        vp.get_attestation(999)


def test_seconds_to_close_tracks_the_state(vp, direct_vm, direct_alice, direct_bob):
    aid = request(vp, direct_vm, direct_alice)
    direct_vm.sender = direct_alice
    set_time(iso(T0 + 10))
    assert int(vp.get_attestation(aid)["seconds_to_close"]) == ATTEST_WINDOW + SLACK - 10
    mock_verdict(direct_vm)
    attest(vp, direct_vm, direct_bob, aid)
    direct_vm.sender = direct_alice
    set_time(iso(T0 + COOLDOWN + 10))
    # the verdict landed one second into the cooldown, so nine seconds of the
    # challenge window are already gone
    assert int(vp.get_attestation(aid)["seconds_to_close"]) == WINDOW - 9


def test_stats_start_empty(vp, direct_vm, direct_alice):
    stats = vp.get_stats()
    assert int(stats["attestations"]) == 0
    assert int(stats["held"]) == 0
    assert int(stats["bonds_held"]) == 0
    assert int(stats["rewarded"]) == 0
    assert int(stats["refunded"]) == 0


# ----------------------------------------------------------------- regression
# Steward requirement: every accepted challenge must have at least one executable
# re-review attempt, including when the original verdict was reached on round three.
# This test demonstrates the full path: 3 attestation rounds -> challenge -> 1 re_review.
def test_challenge_after_max_attestation_rounds_still_has_re_review(
    vp, direct_vm, direct_alice, direct_bob, direct_charlie
):
    """Attestation burns 3 rounds (max), then a challenge is raised.
    The challenge gets its own MAX_CHALLENGE_ROUNDS budget, so re_review is executable."""
    aid = request(vp, direct_vm, direct_alice)

    # Round 1: UNRENDERABLE
    assert attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * 2) == "UNRENDERABLE"
    # Round 2: UNRENDERABLE
    assert attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * 4) == "UNRENDERABLE"
    # Round 3: CONFIRMED (verdict lands on max round)
    mock_verdict(direct_vm, "CONFIRMED")
    assert attest(vp, direct_vm, direct_bob, aid, at=T0 + COOLDOWN * 6) == "CONFIRMED"

    a = vp.get_attestation(aid)
    assert a["status"] == "ATTESTED"
    assert a["verdict"] == "CONFIRMED"
    assert int(a["rounds"]) == 3
    assert int(a["max_rounds"]) == 3

    # Challenge after max attestation rounds
    call(
        direct_vm,
        lambda: vp.challenge(aid, "the page actually says refused"),
        direct_charlie,
        FEE,
        T0 + COOLDOWN * 7,
    )
    a = vp.get_attestation(aid)
    assert a["status"] == "CHALLENGED"
    assert int(a["challenge_rounds"]) == 0
    assert int(a["max_challenge_rounds"]) == 3

    # Re-review is executable because challenge_rounds < MAX_CHALLENGE_ROUNDS
    mock_verdict(direct_vm, "REFUTED")  # flip the verdict
    result = call(
        direct_vm,
        lambda: vp.re_review(aid),
        direct_bob,
        0,
        T0 + COOLDOWN * 9,
    )
    assert result == "OVERTURNED"
    a = vp.get_attestation(aid)
    assert a["status"] == "OVERTURNED"
    assert a["verdict"] == "REFUTED"
    assert int(a["challenge_rounds"]) == 1
