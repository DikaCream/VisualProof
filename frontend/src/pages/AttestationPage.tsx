import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useVisualProof } from "../context/VisualProofContext";
import { StatusLamp, VerdictStamp } from "../components/Chrome";
import {
  EXPLORER_ADDR,
  formatClock,
  formatGen,
  hostOf,
  MAX_REASON,
  shortHex,
  untilClock,
} from "../config";
import { Attestation, STATUS_LABEL } from "../lib/types";

function sameAddr(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  return a.replace(/^addr#/, "0x").toLowerCase() === b.replace(/^addr#/, "0x").toLowerCase();
}

export function AttestationPage() {
  const { id } = useParams();
  const attId = parseInt(id || "0", 10);
  const { read, run, busy, wallet, version, refresh } = useVisualProof();
  const [att, setAtt] = useState<Attestation | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [readFailed, setReadFailed] = useState(false);
  const [grounds, setGrounds] = useState("");
  const [nowSec, setNowSec] = useState(Math.floor(Date.now() / 1000));

  useEffect(() => {
    let alive = true;
    setReadFailed(false);
    if (!Number.isFinite(attId) || attId < 1) {
      setLoadError("That attestation does not exist on this contract.");
      return () => {
        alive = false;
      };
    }
    read
      .getAttestation(attId)
      .then((a) => {
        if (!alive) return;
        if (!a) setLoadError("That attestation does not exist on this contract.");
        else setAtt(a);
      })
      .catch(() => {
        // a dropped RPC request is not a missing record, and saying so would be
        // a lie the visitor cannot recover from
        if (alive) setReadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [read, attId, version]);

  // the windows are on-chain seconds, so re-render against a ticking clock
  useEffect(() => {
    const t = setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(t);
  }, []);

  if (readFailed) {
    return (
      <div className="page narrow">
        <div className="note bad">
          The network did not answer while reading this attestation. That is a dropped request, not a
          missing record: the verdict on chain has not gone anywhere.
        </div>
        <div className="cta-row">
          <button className="btn primary" onClick={refresh}>
            Read it again
          </button>
          <Link className="btn ghost" to="/">
            Back to the board
          </Link>
        </div>
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="page narrow">
        <div className="note bad">{loadError}</div>
        <div className="cta-row">
          <Link className="btn ghost" to="/">
            Back to the board
          </Link>
        </div>
      </div>
    );
  }
  if (!att) {
    return (
      <div className="page narrow">
        <div className="empty">Reading the attestation...</div>
      </div>
    );
  }

  const me = wallet.address;
  const isRequester = sameAddr(me, att.requester);
  const isVerifier = sameAddr(me, att.verifier);
  const isChallenger = sameAddr(me, att.challenger);
  const windowOpen = att.secondsToClose > 0;
  const closesAt = nowSec + att.secondsToClose;

  async function act(label: string, fn: (c: any) => Promise<string>) {
    await run(label, fn);
  }

  return (
    <div className="page narrow">
      <div className="att-top">
        <h1>Attestation #{att.id}</h1>
        <StatusLamp status={att.status} />
      </div>

      <div className="claim-box">
        <span className="label">The claim</span>
        <p className="claim-text">{att.claim}</p>
        {att.purpose && <p className="mini-note">Purpose: {att.purpose}</p>}
      </div>

      <div className="att-facts">
        <div>
          <span>Target</span>
          <b>
            <a href={att.targetUrl} target="_blank" rel="noreferrer" className="mono">
              {hostOf(att.targetUrl)}
            </a>
          </b>
        </div>
        <div>
          <span>Evidence</span>
          <b className="mono">{att.evidence === "visual" ? "screenshot (vision)" : "rendered text"}</b>
        </div>
        <div>
          <span>Fee</span>
          <b className="mono">{formatGen(att.fee)} GEN</b>
        </div>
        <div>
          <span>Challenge bond</span>
          <b className="mono">{formatGen(att.challengeBond)} GEN</b>
        </div>
        <div>
          <span>Requester</span>
          <b>
            <a className="mono" href={EXPLORER_ADDR(att.requester)} target="_blank" rel="noreferrer">
              {shortHex(att.requester)}
              {isRequester ? " (you)" : ""}
            </a>
          </b>
        </div>
        <div>
          <span>Verifier</span>
          <b>
            {att.hasVerifier ? (
              <a className="mono" href={EXPLORER_ADDR(att.verifier)} target="_blank" rel="noreferrer">
                {shortHex(att.verifier)}
                {isVerifier ? " (you)" : ""}
              </a>
            ) : (
              "none yet"
            )}
          </b>
        </div>
      </div>

      {att.verdict && (
        <div className={`verdict ${att.verdict === "CONFIRMED" ? "yes" : "no"}`}>
          <VerdictStamp verdict={att.verdict} confidence={att.confidence} />
          <span>{att.reasoning || "No evidence recorded."}</span>
        </div>
      )}

      <p className="mini-note mono">
        Rounds used: {att.rounds} of {att.maxRounds}
        {att.challenges > 0 ? ` · challenges: ${att.challenges}` : ""}
        {att.challengeVoided ? " · the challenge was voided" : ""}
      </p>

      {/* ---------------- actions, one set per state ---------------- */}
      {att.status === "REQUESTED" && (
        <div className="actions">
          <button
            className="btn primary"
            disabled={!!busy || !wallet.address}
            onClick={() => act("Running the attestation", (c) => c.attest(att.id))}
          >
            Run the attestation
          </button>
          <p className="mini-note">
            Open to anyone. The wallet that runs it becomes the verifier and earns the fee, because
            verification is work the contract pays for.
          </p>
          {!windowOpen && (
            <button
              className="btn ghost"
              disabled={!!busy}
              onClick={() => act("Refunding the stale request", (c) => c.refundStale(att.id))}
            >
              Refund: nobody attested this in time
            </button>
          )}
        </div>
      )}

      {att.status === "ATTESTED" && (
        <div className="actions">
          {windowOpen && (
            <button
              className="btn ghost"
              disabled={!!busy || !wallet.address}
              onClick={() => act("Staking the challenge", (c) => c.challenge(att.id, grounds, att.challengeBond))}
            >
              Challenge: stake {formatGen(att.challengeBond)} GEN
            </button>
          )}
          {windowOpen && (
            <label className="field">
              <span>Grounds (optional, shown in the record)</span>
              <input
                className="mono"
                value={grounds}
                onChange={(e) => setGrounds(e.target.value)}
                maxLength={MAX_REASON}
                placeholder="Why this verdict is wrong"
              />
            </label>
          )}
          {!windowOpen && (
            <button
              className="btn primary"
              disabled={!!busy}
              onClick={() => act("Paying the verifier", (c) => c.claimReward(att.id))}
            >
              Release the reward to the verifier
            </button>
          )}
          <p className="mini-note">
            {windowOpen
              ? `A challenge re-runs the judgement against a fresh render. It closes ${formatClock(closesAt)} (${untilClock(closesAt, nowSec)}).`
              : att.challengeVoided
                ? "The challenge was spent without a verdict, so the reward releases now and the record stands."
                : "The window closed clean: the reward is released to the verifier."}
          </p>
        </div>
      )}

      {att.status === "CHALLENGED" && (
        <div className="actions">
          {windowOpen ? (
            <button
              className="btn primary"
              disabled={!!busy || !wallet.address}
              onClick={() => act("Running the re-review", (c) => c.reReview(att.id))}
            >
              Run the re-review
            </button>
          ) : (
            <button
              className="btn primary"
              disabled={!!busy}
              onClick={() => act("Finalizing the challenge", (c) => c.finalizeChallenge(att.id))}
            >
              Finalize: the window passed with no re-review
            </button>
          )}
          <p className="mini-note">
            {windowOpen
              ? `A re-review that agrees upholds the record and the challenger's bond pays the verifier. A re-review that flips it corrects the record and returns the fee to the requester. Closes ${formatClock(closesAt)}.`
              : "Nobody ran the re-review inside the window, so the record stands and the bond goes back to the challenger."}
          </p>
          {att.hasChallenger && (
            <p className="mini-note mono">
              Challenger{isChallenger ? " (you)" : ""}: {shortHex(att.challenger)}
            </p>
          )}
        </div>
      )}

      {att.isTerminal && (
        <div className="actions">
          <p className="mini-note">
            Closed: {STATUS_LABEL[att.status] ?? att.status}.
            {att.status === "REWARDED" && ` The verifier was paid ${formatGen(att.fee)} GEN.`}
            {att.status === "UPHELD" && " The challenge failed and the verifier was paid the reward plus the bond."}
            {att.status === "OVERTURNED" && " The record was corrected: the fee went back to the requester and the bond to the challenger."}
            {att.status === "REFUNDED" && " The fee went back to the requester in full: no verdict, no payment."}
          </p>
        </div>
      )}

      <p className="foot-note mono">
        The page is evidence, never an authority · the contract takes no cut ·{" "}
        <Link to="/">back to the board</Link>
      </p>
    </div>
  );
}
