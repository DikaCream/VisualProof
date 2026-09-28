/** Contract reverts and wallet failures, translated into next-step guidance. */

const RULES: Array<[RegExp, string]> = [
  [/fee is below the minimum/i, "The fee must be at least 0.01 GEN. That fee is the verifier's reward."],
  [/url: 1-/i, "The target URL needs 1 to 500 characters."],
  [/url must be a public http url/i, "The target must be a public http(s) page."],
  [/publicly renderable/i, "That host cannot be rendered publicly: localhost, private ranges, numeric IP spellings and wildcard-DNS hosts are rejected."],
  [/claim: 1-/i, "The claim needs 1 to 400 characters and cannot be blank."],
  [/purpose: max/i, "Keep the purpose under 300 characters."],
  [/evidence must be/i, "Pick an evidence mode: visual (screenshot) or text."],
  [/attestation not found/i, "That attestation does not exist on this contract."],
  [/not open for attestation/i, "This request is no longer open: it has a verdict, was challenged, or was refunded."],
  [/rounds exhausted/i, "The rounds ran out on this one. It should refund through the stale path."],
  [/cooldown between rounds/i, "Another round can run one minute after the last one."],
  [/nothing to reward/i, "There is nothing to reward here: this attestation has no standing verdict."],
  [/challenge window still open/i, "The challenge window is still open. The reward unlocks once it closes."],
  [/only a standing verdict/i, "Only an attestation with a standing verdict can be challenged."],
  [/already challenged/i, "This attestation was already challenged once. The challenge is single shot."],
  [/challenge window closed/i, "The challenge window has closed on this attestation."],
  [/grounds: max/i, "Keep the grounds under 500 characters."],
  [/exactly this attestation's challenge bond/i, "Send exactly this attestation's challenge bond."],
  [/no challenge is pending/i, "No challenge is pending on this attestation."],
  [/re-review window closed/i, "The re-review window has closed."],
  [/re-review window still open/i, "The re-review window is still open. Finalize becomes possible once it closes."],
  [/only an unattested request/i, "Only a request nobody attested can be refunded here."],
  [/not closed yet/i, "The attestation window plus its grace period has not elapsed yet."],
  [/bad pagination/i, "Bad pagination: 1 to 50 per page."],
  [/user rejected/i, "The request was rejected in the wallet."],
  [/insufficient funds/i, "The wallet does not cover the amount plus gas."],
  [/chain|network/i, "The wallet is on the wrong network. Switch to GenLayer StudioNet."],
];

export function describeError(e: unknown): string {
  const raw = typeof e === "string" ? e : ((e as any)?.message ?? (e as any)?.shortMessage ?? String(e));
  const text = String(raw);

  for (const [pattern, friendly] of RULES) {
    if (pattern.test(text)) return friendly;
  }
  if (/fetch|network|timeout/i.test(text)) {
    return "The network did not answer. Check the connection and try again.";
  }
  const match = text.match(/UserError[^"]*"([^"]{3,160})"/);
  if (match) return match[1];
  const quoted = text.match(/"([^"]{10,160})"/);
  if (quoted) return quoted[1];
  return text.slice(0, 200) || "Something went wrong. Try again.";
}
