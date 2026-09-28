export type AttestationStatus =
  | "REQUESTED"
  | "ATTESTED"
  | "CHALLENGED"
  | "REWARDED"
  | "UPHELD"
  | "OVERTURNED"
  | "REFUNDED";

export type Evidence = "visual" | "text";

export interface Attestation {
  id: number;
  requester: string;
  verifier: string;
  hasVerifier: boolean;
  challenger: string;
  hasChallenger: boolean;
  fee: bigint;
  challengeBond: bigint;
  targetUrl: string;
  claim: string;
  purpose: string;
  evidence: Evidence;
  status: AttestationStatus;
  verdict: string;
  reasoning: string;
  confidence: string;
  rounds: number;
  maxRounds: number;
  challenges: number;
  challengeVoided: boolean;
  challengedAt: number;
  verdictAt: number;
  requestedAt: number;
  secondsToClose: number;
  isTerminal: boolean;
}

export interface AttestationSummary {
  id: number;
  fee: bigint;
  status: AttestationStatus;
  verdict: string;
  targetUrl: string;
  claim: string;
  evidence: Evidence;
  hasVerifier: boolean;
  requester: string;
  verifier: string;
  requestedAt: number;
}

export interface Stats {
  attestations: number;
  attested: number;
  confirmed: number;
  refuted: number;
  challenged: number;
  overturned: number;
  voidRounds: number;
  held: bigint;
  rewarded: bigint;
  refunded: bigint;
  bondsHeld: bigint;
  bondPayouts: bigint;
}

function addr(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "object") {
    const anyV = v as Record<string, unknown>;
    if ("as_hex" in anyV) return String(anyV.as_hex);
    if ("_as_hex" in anyV) return String(anyV._as_hex);
    if ("hex" in anyV) return String(anyV.hex);
  }
  return String(v);
}

function big(v: unknown): bigint {
  try {
    if (typeof v === "bigint") return v;
    if (typeof v === "string") return v.startsWith("addr#") ? 0n : BigInt(v);
    if (typeof v === "number") return BigInt(v);
  } catch {
    /* keep 0 */
  }
  return 0n;
}

function num(v: unknown): number {
  return Number(big(v));
}

function evidence(v: unknown): Evidence {
  return String(v ?? "visual").toLowerCase() === "text" ? "text" : "visual";
}

export function toAttestation(v: any): Attestation {
  return {
    id: num(v.id),
    requester: addr(v.requester),
    verifier: addr(v.verifier),
    hasVerifier: Boolean(v.has_verifier),
    challenger: addr(v.challenger),
    hasChallenger: Boolean(v.has_challenger),
    fee: big(v.fee),
    challengeBond: big(v.challenge_bond),
    targetUrl: String(v.target_url ?? ""),
    claim: String(v.claim ?? ""),
    purpose: String(v.purpose ?? ""),
    evidence: evidence(v.evidence),
    status: String(v.status ?? "REQUESTED") as AttestationStatus,
    verdict: String(v.verdict ?? ""),
    reasoning: String(v.reasoning ?? ""),
    confidence: String(v.confidence ?? ""),
    rounds: num(v.rounds),
    maxRounds: num(v.max_rounds) || 3,
    challenges: num(v.challenges),
    challengeVoided: Boolean(v.challenge_voided),
    challengedAt: num(v.challenged_at),
    verdictAt: num(v.verdict_at),
    requestedAt: num(v.requested_at),
    secondsToClose: num(v.seconds_to_close),
    isTerminal: Boolean(v.is_terminal),
  };
}

export function toAttestationSummary(v: any): AttestationSummary {
  return {
    id: num(v.id),
    fee: big(v.fee),
    status: String(v.status ?? "REQUESTED") as AttestationStatus,
    verdict: String(v.verdict ?? ""),
    targetUrl: String(v.target_url ?? ""),
    claim: String(v.claim ?? ""),
    evidence: evidence(v.evidence),
    hasVerifier: Boolean(v.has_verifier),
    requester: addr(v.requester),
    verifier: addr(v.verifier),
    requestedAt: num(v.requested_at),
  };
}

export function toStats(v: any): Stats {
  return {
    attestations: num(v.attestations),
    attested: num(v.attested),
    confirmed: num(v.confirmed),
    refuted: num(v.refuted),
    challenged: num(v.challenged),
    overturned: num(v.overturned),
    voidRounds: num(v.void_rounds),
    held: big(v.held),
    rewarded: big(v.rewarded),
    refunded: big(v.refunded),
    bondsHeld: big(v.bonds_held),
    bondPayouts: big(v.bond_payouts),
  };
}

export const STATUS_LABEL: Record<string, string> = {
  REQUESTED: "awaiting an attestation",
  ATTESTED: "verdict standing, challenge window open",
  CHALLENGED: "challenged, re-review pending",
  REWARDED: "verifier paid",
  UPHELD: "challenge failed, record stands",
  OVERTURNED: "record corrected",
  REFUNDED: "refunded, no verdict",
};
