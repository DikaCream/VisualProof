import { Link } from "react-router-dom";
import { useVisualProof } from "../context/VisualProofContext";
import { StatusLamp } from "../components/Chrome";
import { CONTRACT_ADDRESS, EXPLORER_ADDR, formatGen, hostOf } from "../config";
import { AttestationSummary } from "../lib/types";

function nextAction(a: AttestationSummary): string {
  switch (a.status) {
    case "REQUESTED":
      return "Run the attestation";
    case "ATTESTED":
      return "Claim the reward or challenge";
    case "CHALLENGED":
      return "Run the re-review";
    default:
      return "Closed";
  }
}

export function Board() {
  const { attestations, stats, loading, error, refresh } = useVisualProof();

  return (
    <div className="page">
      <section className="hero">
        <p className="kicker">GenLayer StudioNet · consensus vision</p>
        <h1>What a page actually shows, decided by consensus</h1>
        <p>
          Anyone pays a fee and writes a claim about a public page. Validators render that page to a
          screenshot, read it with a vision model, and must land on the same verdict before the
          attestation is written. The page is evidence. The verdict is consensus output.
        </p>
        <div className="cta-row">
          <Link className="btn primary" to="/new">
            Request an attestation
          </Link>
          <Link className="btn ghost" to="/how">
            How the judgement works
          </Link>
        </div>
      </section>

      <section className="stats-row" aria-label="Contract totals">
        <div className="stat">
          <i className="stat-num mono">{stats.attestations}</i>
          <span>attestations requested</span>
        </div>
        <div className="stat">
          <i className="stat-num mono">
            {stats.confirmed}
            <small> / {stats.refuted}</small>
          </i>
          <span>confirmed / refuted</span>
        </div>
        <div className="stat">
          <i className="stat-num mono">{stats.overturned}</i>
          <span>records corrected on challenge</span>
        </div>
        <div className="stat">
          <i className="stat-num mono">{formatGen(stats.held + stats.bondsHeld)}</i>
          <span>GEN held for verifiers and bonds</span>
        </div>
      </section>

      <section className="board-head">
        <h2>Standing attestations</h2>
        <span className="mini mono">
          {stats.voidRounds} round{stats.voidRounds === 1 ? "" : "s"} produced no verdict
        </span>
      </section>

      {loading && <div className="empty">Reading the contract...</div>}
      {error && !loading && (
        <>
          <div className="empty bad">Could not read the contract: {error}</div>
          <div className="cta-row">
            <button className="btn primary" onClick={refresh}>
              Read it again
            </button>
          </div>
        </>
      )}
      {!loading && !error && attestations.length === 0 && (
        <div className="empty">No attestation stands yet. Request the first one.</div>
      )}

      <div className="att-list">
        {attestations.map((a) => (
          <Link to={`/attestations/${a.id}`} key={a.id} className="att-row">
            <span className="att-id mono">#{a.id}</span>
            <StatusLamp status={a.status} />
            <span className="att-mode mono">{a.evidence === "visual" ? "screenshot" : "text"}</span>
            <span className="att-claim">{a.claim}</span>
            <span className="att-host mono">{hostOf(a.targetUrl)}</span>
            <span className="att-action">{nextAction(a)}</span>
            <span className="att-clock mono">{formatGen(a.fee)} GEN fee</span>
          </Link>
        ))}
      </div>

      <p className="foot-note mono">
        Contract:{" "}
        {CONTRACT_ADDRESS ? (
          <a href={EXPLORER_ADDR(CONTRACT_ADDRESS)} target="_blank" rel="noreferrer">
            {CONTRACT_ADDRESS.slice(0, 8)}...{CONTRACT_ADDRESS.slice(-5)}
          </a>
        ) : (
          <span className="bad">not configured</span>
        )}{" "}
        on GenLayer StudioNet
      </p>
    </div>
  );
}
