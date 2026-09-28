import { useVisualProof } from "../context/VisualProofContext";
import { CHAIN_ID_HEX, CHAIN_NAME, EXPLORER_TX, formatGen, shortHex } from "../config";
import { AttestationStatus, STATUS_LABEL } from "../lib/types";

const TONE: Record<string, string> = {
  REQUESTED: "open",
  ATTESTED: "ready",
  CHALLENGED: "appealed",
  REWARDED: "paid",
  UPHELD: "paid",
  OVERTURNED: "returned",
  REFUNDED: "returned",
};

export function WalletButton() {
  const { wallet } = useVisualProof();

  if (!wallet.hasProvider) {
    return (
      <a className="btn ghost small" href="https://metamask.io/download/" target="_blank" rel="noreferrer">
        Install a wallet
      </a>
    );
  }
  if (wallet.address) {
    return (
      <span className="wallet-chip" title={wallet.address}>
        <span className="mono">{formatGen(wallet.balance)} GEN</span>
        <span className="mono addr">{shortHex(wallet.address)}</span>
      </span>
    );
  }
  return (
    <button className="btn primary small" onClick={wallet.connect} disabled={wallet.busy}>
      {wallet.busy ? "Connecting..." : "Connect wallet"}
    </button>
  );
}

export function StatusLamp({ status }: { status: AttestationStatus }) {
  const tone = TONE[status] ?? "open";
  return (
    <span className="lamp" title={STATUS_LABEL[status] ?? status}>
      <i className={`lamp-dot ${tone}`} aria-hidden="true" />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function VerdictStamp({ verdict, confidence }: { verdict: string; confidence?: string }) {
  if (!verdict || (verdict !== "CONFIRMED" && verdict !== "REFUTED")) return null;
  const no = verdict === "REFUTED";
  return (
    <span className={`stamp ${no ? "no" : "yes"}`}>
      {verdict}
      {confidence ? <em>{confidence} confidence</em> : null}
    </span>
  );
}

export function TxBanner() {
  const { txError, lastTx, dismissTx } = useVisualProof();
  if (!txError && !lastTx) return null;
  return (
    <div className={`banner ${txError ? "bad" : "good"}`} role="status">
      <span>{txError ?? "The transaction landed."}</span>
      {lastTx && !txError && (
        <a href={EXPLORER_TX(lastTx)} target="_blank" rel="noreferrer" className="mono">
          {shortHex(lastTx)}
        </a>
      )}
      <button className="x" onClick={dismissTx} aria-label="Dismiss">
        x
      </button>
    </div>
  );
}

/** The wallet is on a different chain than the one the SDK reads: say so. */
export function ChainNotice({ chainId }: { chainId: string | null }) {
  if (!chainId) return null;
  if (chainId.toLowerCase() === CHAIN_ID_HEX.toLowerCase()) return null;
  return (
    <div className="banner bad" role="status">
      <span>This wallet is not on {CHAIN_NAME}. Switch networks before sending a transaction.</span>
    </div>
  );
}
