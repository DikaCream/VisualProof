import { studionet } from "genlayer-js/chains";

/**
 * The chain comes from genlayer-js rather than a hand-written id, so the wallet
 * request and the SDK can never disagree about which network this is. A
 * hardcoded chain id is the kind of detail that keeps working in the SDK and
 * silently fails in `wallet_switchEthereumChain`.
 */
export const CHAIN = studionet;
export const CHAIN_ID = studionet.id;
export const CHAIN_ID_HEX = "0x" + studionet.id.toString(16);
export const CHAIN_NAME = studionet.name;
export const RPC_URL = (studionet.rpcUrls?.default?.http?.[0] as string) ?? "";

/** The deployed VisualProof contract. Set VITE_CONTRACT_ADDRESS per deploy. */
export const CONTRACT_ADDRESS =
  (import.meta.env.VITE_CONTRACT_ADDRESS as string) || "0xFffEbFDb9117EB5F247C8753AfB5d511653C3C10";

export const isConfigured = (): boolean => /^0x[0-9a-fA-F]{40}$/.test(CONTRACT_ADDRESS);

export const EXPLORER_TX = (hash: string) => `https://explorer-studio.genlayer.com/tx/${hash}`;
export const EXPLORER_ADDR = (address: string) =>
  `https://explorer-studio.genlayer.com/address/${address}`;

export const REPO_URL = "https://github.com/DikaCream/VisualProof";
export const CONTRACT_SOURCE_URL =
  "https://raw.githubusercontent.com/DikaCream/VisualProof/main/contracts/visual_proof.py";

export const GEN = 10n ** 18n;

/** Mirrored from the contract so the UI never quotes a number the chain does not use. */
export const MIN_FEE = GEN / 100n; // 0.01 GEN
export const CHALLENGE_WINDOW = 24 * 3600; // seconds
export const ATTEST_WINDOW = 3 * 24 * 3600;
export const DETACH_SLACK = 3600;
export const MAX_ROUNDS = 3;
export const MAX_CLAIM = 400;
export const MAX_PURPOSE = 300;
export const MAX_URL = 500;
export const MAX_REASON = 500;

export function toBigInt(value: bigint | number | string | null | undefined): bigint {
  try {
    if (typeof value === "bigint") return value;
    if (value === null || value === undefined) return 0n;
    return BigInt(value);
  } catch {
    return 0n;
  }
}

/** GEN amounts stay legible: four decimals, no wall of zeros. */
export function formatGen(value: bigint | number | string, maxDecimals = 4): string {
  let wei = toBigInt(value);
  const negative = wei < 0n;
  if (negative) wei = -wei;
  const scale = 10n ** BigInt(maxDecimals);
  const whole = wei / GEN;
  const frac = ((wei % GEN) * scale) / GEN;
  const fracStr = frac.toString().padStart(maxDecimals, "0").replace(/0+$/, "");
  if (whole === 0n) {
    if (fracStr === "") return wei === 0n ? "0" : `<0.${"0".repeat(maxDecimals - 1)}1`;
    return `${negative ? "-" : ""}0.${fracStr}`;
  }
  return `${negative ? "-" : ""}${whole}${fracStr ? `.${fracStr}` : ""}`;
}

export function shortHex(a: string, lead = 6, tail = 4): string {
  if (!a) return "";
  const hex = a.startsWith("addr#") ? "0x" + a.slice(5) : a;
  if (hex.length <= lead + tail + 3) return hex;
  return `${hex.slice(0, lead)}...${hex.slice(-tail)}`;
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatClock(unix: number): string {
  if (!unix) return "n/a";
  const d = new Date(unix * 1000);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()} ${pad(
    d.getUTCHours(),
  )}:${pad(d.getUTCMinutes())} UTC`;
}

export function untilClock(unix: number, nowSec = Math.floor(Date.now() / 1000)): string {
  const s = unix - nowSec;
  if (s <= 0) return "passed";
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h left`;
  if (h > 0) return `${h}h ${m}m left`;
  return `${m}m left`;
}
