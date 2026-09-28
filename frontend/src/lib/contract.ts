import { CONTRACT_ADDRESS } from "../config";
import { Attestation, AttestationSummary, Stats, toAttestation, toAttestationSummary, toStats } from "./types";

export class VisualProof {
  constructor(private client: any, private address: string = CONTRACT_ADDRESS) {}

  private async read(functionName: string, args: unknown[] = []): Promise<any> {
    return this.client.readContract({ address: this.address as `0x${string}`, functionName, args });
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
    return toStats(await this.read("get_stats"));
  }

  async getAttestation(id: number): Promise<Attestation | null> {
    try {
      const v = await this.read("get_attestation", [id]);
      if (v == null) return null;
      return toAttestation(v);
    } catch {
      return null;
    }
  }

  async listAttestations(offset = 0, limit = 50, mineOnly = false): Promise<AttestationSummary[]> {
    const v = await this.read("list_attestations", [offset, limit, mineOnly]);
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
