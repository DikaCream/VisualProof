# VisualProof

Attestations about what a public page actually shows, decided by GenLayer
consensus. Anyone pays a fee and writes one yes/no claim about a public page. A
validator renders that page to a screenshot, reads it with a vision model, and
answers CONFIRMED or REFUTED. The comparative equivalence principle refuses to
write anything until the independent judgements agree, so the verdict is
consensus output and the page is evidence, never an authority.

## Why pixels and not markup

A host can serve different bytes per user agent, hide the claimed thing behind a
consent overlay, or keep the claimed string in the HTML without ever painting
it. A text fetch cannot tell the difference. Rendering the page and reading what
was drawn can, which is why visual mode exists at all.

Two evidence modes are offered, because two different questions are worth
asking:

- **visual** renders the URL to a screenshot and judges what is painted.
- **text** reads the rendered text, which is cheaper and enough for a claim
  about a string.

## The machine

```
REQUESTED -> ATTESTED -> REWARDED      window closed clean: verifier paid
REQUESTED -> REFUNDED                  nobody attested, or no verdict in 3 rounds
ATTESTED  -> CHALLENGED -> UPHELD      re-review agrees: bond forfeits to verifier
ATTESTED  -> CHALLENGED -> OVERTURNED  re-review flips: fee back to the requester
CHALLENGED -> ATTESTED                 rounds ran out: record stands, bond returns
```

Money paths, each guarded:

- The requester's fee is the verifier's reward. The contract takes no cut, so
  there is no owner to collect anything and no balance that can be stranded.
- The reward is held, not paid, until the challenge window closes: a record
  that can still be corrected should not be paid out yet.
- OVERTURNED returns the fee to the requester, because the answer they paid for
  was wrong, and returns the bond to the challenger.
- UPHELD pays the verifier the reward plus the challenger's bond.
- A challenge that never reaches a verdict returns the bond and frees the
  reward, because a page that cannot be rendered is nobody's fault.
- REFUNDED returns the fee in full: no verdict, no payment.
- Every payout is capped by what that attestation actually holds, and the
  held/bond totals move in the same step as every transfer.

Constants: `MIN_FEE` 0.01 GEN, `MIN_CHALLENGE_BOND` 0.01 GEN, `ATTEST_WINDOW` 3
days, `CHALLENGE_WINDOW` 1 day, `REVIEW_COOLDOWN` 60 s, `MAX_ROUNDS` 3.

## The URL gate

Validators must be able to render the page, so a host only the requester can
reach must never be judged. Hosts are canonicalised before they are checked,
because the cheap bypasses are spelling games:

| Attempt | Rejected because |
|---|---|
| `127.0.0.1`, `10.x`, `192.168.x`, `172.16-31.x`, `169.254.x`, `100.64-127.x` | private ranges |
| `127.1`, `2130706433`, `0x7f000001`, `0177.0.0.1` | numeric spellings of an IP |
| `8.8.8.8` | a public page has a hostname, not a bare address |
| `localhost.`, `metadata.google.internal.` | the trailing root dot is stripped first |
| `example.com:8080@127.1` | userinfo ends at the last `@`, so the host is `127.1` |
| `127.0.0.1.nip.io`, `169.254.169.254.nip.io`, `box.lvh.me` | wildcard-DNS services resolve wherever you like |

Known limit, by design: the contract cannot resolve DNS, so a host that simply
does not exist passes the gate and then burns rounds. That is what the
three-round force refund is for, and the seed board demonstrates it.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp gltest.config.example.yaml gltest.config.yaml   # then add your StudioNet keys
```

## Tests

Direct mode, in a local VM with mocked renders and mocked verdicts:

```bash
python -m pytest tests/direct/test_visual_proof.py -q
```

Every guard was mutation checked: each one was disabled in turn, the matching
test failed, and the guard came back.

Vision cannot be covered here, and the reason is worth stating plainly: the
local VM's `render(mode="screenshot")` returns an empty image no matter what is
mocked, so any vision claim can only be settled on a live network. The suite
asserts that an empty image burns a round instead of settling anyone, and the
network run below is where real pixels are exercised.

## On StudioNet

Smoke test first, because everything downstream depends on it:

```bash
gltest --network studionet tests/smoke_vision.py -v -s
```

Then the board seed, which deploys a fresh contract and walks every state it
can reach in one run:

```bash
gltest --network studionet tests/deploy_seed_visualproof.py -v -s
```

It prints `VISUALPROOF_ADDRESS=0x...` at the end. That address is what the
frontend reads.

## Frontend

```bash
cd frontend
npm install
VITE_CONTRACT_ADDRESS=0x... npm run dev
```

Pages: the attestation board, a request form, and one page per attestation with
the actions that state actually allows.

## License

MIT.
