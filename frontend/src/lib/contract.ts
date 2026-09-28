import { CONTRACT_ADDRESS } from "../config";
import { Attestation, AttestationSummary, Stats, toAttestation, toAttestationSummary, toStats } from "./types";

/** A missing record is a fact; a failed fetch is a hiccup that deserves a retry. */
const NOT_FOUND = /attestation not found/i;
const TRANSIENT = /failed to fetch|networkerror|network error|timeout|timed out|fetch failed|gen_call|502|503|504/i;

function messageOf(e: unknown): string {
  return String((e as any)?.message ?? (e as any)?.shortMessage ?? e);
}

export class VisualProof {
  constructor(private client: any, private address: string = CONTRACT_ADDRESS) {}

  private async read(functionName: string, args: unknown[] = []): Promise<any> {
    return this.client.readContract({ address: this.address as `0x${string}`, functionName, args });
  }

  /**
   * Reads go over a public RPC, so a dropped request is normal: under a burst
   * of page loads the endpoint answers "Failed to fetch" often enough that a
   * user would see an error page for a hiccup. Retry with backoff, and never
   * retry a real revert.
   */
  private async readWithRetry<T>(fn: () => Promise<T>, tries = 5): Promise<T> {
    let last: unknown;
    for (let attempt = 0; attempt < tries; attempt++) {
      try {
        return await fn();
      } catch (e) {
        last = e;
        const msg = messageOf(e);
        if (NOT_FOUND.test(msg) || !TRANSIENT.test(msg)) throw e;
        if (attempt < tries - 1) await new Promise((r) => setTimeout(r, 350 * 2 ** attempt));
      }
    }
    throw last;
  }

  private async write(functionName: string, args: unknown[], value: bigint = 0n): Promise<string> {
    return (await this.client.writeContract({
      address: this.address as `0x${string}`,
      functionName,
      args,
      value,
    })) as string;
  }

  async waitForReceipt(txHash: string, retries = 90, interval = 3000): Promise<any> {
    return this.client.waitForTransactionReceipt({
      hash: txHash,
      status: "ACCEPTED" as any,
      retries,
      interval,
    });
  }

  // ---- reads ----------------------------------------------------------
  async getStats(): Promise<Stats> {
    return toStats(await this.readWithRetry(() => this.read("get_stats")));
  }

  /**
   * Returns null only when the contract says the record does not exist. A
   * transport failure throws, because reporting a dropped request as "this
   * attestation does not exist" is a lie the user cannot recover from.
   */
  async getAttestation(id: number): Promise<Attestation | null> {
    try {
      const v = await this.readWithRetry(() => this.read("get_attestation", [id]));
      if (v == null) return null;
      return toAttestation(v);
    } catch (e) {
      if (NOT_FOUND.test(messageOf(e))) return null;
      throw e;
    }
  }

  async listAttestations(offset = 0, limit = 50, mineOnly = false): Promise<AttestationSummary[]> {
    const v = await this.readWithRetry(() => this.read("list_attestations", [offset, limit, mineOnly]));
    return Array.isArray(v) ? v.map(toAttestationSummary) : [];
  }

  // ---- writes ---------------------------------------------------------
  requestAttestation(url: string, claim: string, purpose: string, evidence: string, feeWei: bigint) {
    return this.write("request_attestation", [url, claim, purpose, evidence], feeWei);
  }

  attest(id: number) {
    return this.write("attest", [id]);
  }

  challenge(id: number, grounds: string, bondWei: bigint) {
    return this.write("challenge", [id, grounds], bondWei);
  }

  reReview(id: number) {
    return this.write("re_review", [id]);
  }

  claimReward(id: number) {
    return this.write("claim_reward", [id]);
  }

  refundStale(id: number) {
    return this.write("refund_stale", [id]);
  }

  finalizeChallenge(id: number) {
    return this.write("finalize_challenge", [id]);
  }
}
