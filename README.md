# VisualProof

Attestations about what a public page actually shows, decided by GenLayer
consensus. Anyone pays a fee and writes one yes/no claim about a public page. A
validator renders that page to a screenshot, reads it with a vision model, and
answers CONFIRMED or REFUTED. The comparative equivalence principle refuses to
write anything until the independent judgements agree, so the verdict is
consensus output and the page is evidence, never an authority.

## Try it

- App: https://visualproof-gamma.vercel.app
- Repo: https://github.com/DikaCream/VisualProof
- Contract on StudioNet: `0x3Ab5b60C4649A5DA80618EB179E18b49f50478B7`

The seeded board carries six attestations and every state a single run can reach:

- **#1, REQUESTED.** Open. Anyone can run the attestation from the app and watch
  consensus render the page and settle the claim.
- **#2, ATTESTED, visual.** `CONFIRMED` from a real screenshot. The reasoning on
  chain reads: *"The screenshot clearly displays the text 'Example Domain' in a
  large, bold font at the top of the content area, serving as a heading."* The
  challenge window closes a day after the verdict; after that anyone can release
  the fee to the verifier with `claim_reward`.
- **#3, CHALLENGED.** A verdict with a challenge staked on it, bond and all, left
  for a visitor to re-review.
- **#4, UPHELD.** The challenge was staked, the re-review agreed, and the
  challenger's bond paid the verifier.
- **#5, OVERTURNED.** The delivery page was rewritten in place between the
  verdict and the re-review, so the same URL failed the same claim: the record
  was corrected, the fee returned to the requester and the bond to the
  challenger.
- **#6, REFUNDED.** A host that never resolves burned three rounds and the fee
  went back, because a page that cannot be rendered is nobody's fault.

Stats at the time of writing: 6 attestations, 4 attested (3 confirmed, 1
refuted), 3 challenged, 1 overturned, 3 rounds that produced no verdict, 0.03
GEN held for verifiers, 0.01 GEN in a standing bond, 0.01 GEN paid to verifiers,
0.02 GEN refunded. The contract's own balance reads 0.04 GEN, which is exactly
`held + bonds_held`.

### Proof on chain

- Deployment: `0x32ba8df686703b7e189e6abed2afc03b0c7f3dd3afb211817368662ad4e6ed80`
- Attestation #2, the visual `CONFIRMED`: `0x1f6804d763e16e50d173074f2483e5237028b60950e3684e45eb665a8840b3bc`
- Challenge on #4: `0x9359b540af18c654b7a489943da82ba7eb8f671482b9f9d6a8defcc5402b34b6`
- Re-review that upheld it: `0x61ced00102de919854c1e0104e9e030ad61ce576e49651c9a57975a9c8f7900b`
- Re-review that overturned #5: `0xd6c0d95e74363e6a4e555ffc5431733d35df6c468b20e9d8cf32da5de02b736a`
- The round that force-refunded #6: `0x585c26e47552ebb38a0598bb1677bbf71ed08e9a64aa566e2784a272b113cae1`

The vision primitive itself was proved separately first, on a throwaway probe
contract, before any of the state machine was written: that call rendered
`https://example.com/` to a screenshot and consensus returned
`{"has_links": true, "heading": "Example Domain"}`.

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
