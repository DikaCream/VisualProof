import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useVisualProof } from "../context/VisualProofContext";
import { GEN, MAX_CLAIM, MAX_PURPOSE, MAX_URL, MIN_FEE, formatGen } from "../config";

const SAMPLE_CLAIM = "The page shows the word 'BETA' in a visible badge near the top of the page.";
const SAMPLE_PURPOSE = "Checking that a release page carries its beta label before publishing a link to it.";

export function NewAttestation() {
  const { run, busy, wallet } = useVisualProof();
  const navigate = useNavigate();

  const [url, setUrl] = useState("https://example.com/");
  const [claim, setClaim] = useState(SAMPLE_CLAIM);
  const [purpose, setPurpose] = useState(SAMPLE_PURPOSE);
  const [evidence, setEvidence] = useState<"visual" | "text">("visual");
  const [fee, setFee] = useState("0.01");
  const [localError, setLocalError] = useState<string | null>(null);

  // six decimals is the precision the form offers; parse in integer space so
  // 0.01 cannot become 0.009999999
  const feeWei = (() => {
    try {
      const parts = fee.trim().split(".");
      if (parts.length > 2) return 0n;
      const whole = BigInt(parts[0] === "" ? "0" : parts[0]);
      const fracRaw = (parts[1] ?? "").slice(0, 6).padEnd(6, "0");
      if (!/^\d*$/.test(parts[0]) || (parts[1] !== undefined && !/^\d*$/.test(parts[1]))) return 0n;
      return whole * GEN + BigInt(fracRaw) * (GEN / 1000000n);
    } catch {
      return 0n;
    }
  })();

  async function submit() {
    setLocalError(null);
    const u = url.trim();
    if (u.length === 0 || u.length > MAX_URL) {
      setLocalError(`The target URL needs 1 to ${MAX_URL} characters.`);
      return;
    }
    if (!/^https?:\/\//i.test(u)) {
      setLocalError("The target must be a public http(s) page.");
      return;
    }
    if (claim.trim().length === 0 || claim.length > MAX_CLAIM) {
      setLocalError(`The claim needs 1 to ${MAX_CLAIM} characters.`);
      return;
    }
    if (purpose.length > MAX_PURPOSE) {
      setLocalError(`Keep the purpose under ${MAX_PURPOSE} characters.`);
      return;
    }
    if (feeWei < MIN_FEE) {
      setLocalError(`The fee must be at least ${formatGen(MIN_FEE, 3)} GEN.`);
      return;
    }
    const ok = await run("Requesting the attestation", (c) =>
      c.requestAttestation(u, claim.trim(), purpose, evidence, feeWei),
    );
    if (ok) navigate("/");
  }

  return (
    <div className="page narrow">
      <h1>Request an attestation</h1>
      <p className="lede">
        Write one claim a sighted reviewer could settle yes or no, point at the public page it is
        about, and pay the fee that becomes the verifier's reward. The claim is judged against what
        the page renders, never against markup that exists only in the HTML.
      </p>

      {!wallet.address && <div className="note">Connect a wallet to request. Reading needs none.</div>}

      <div className="form">
        <label className="field">
          <span>Target page (public)</span>
          <input className="mono" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." />
          <small>Validators render this URL themselves. localhost, private ranges and numeric IP spellings are rejected.</small>
        </label>

        <label className="field">
          <span>Claim to settle</span>
          <textarea className="mono" rows={3} value={claim} onChange={(e) => setClaim(e.target.value)} maxLength={MAX_CLAIM} />
          <small>One checkable claim, not a request for an opinion. "The page shows X" beats "this page is good".</small>
        </label>

        <label className="field">
          <span>What the answer will be used for</span>
          <textarea className="mono" rows={2} value={purpose} onChange={(e) => setPurpose(e.target.value)} maxLength={MAX_PURPOSE} />
          <small>Context for the verifier. It is never a substitute for what the page shows.</small>
        </label>

        <div className="field-pair">
          <label className="field">
            <span>Evidence mode</span>
            <select className="mono" value={evidence} onChange={(e) => setEvidence(e.target.value as "visual" | "text")}>
              <option value="visual">screenshot (vision)</option>
              <option value="text">rendered text</option>
            </select>
            <small>
              Screenshot is the honest mode for anything about what a page looks like. Text mode is
              cheaper and enough for a claim about a string.
            </small>
          </label>

          <label className="field">
            <span>Fee (GEN)</span>
            <input className="mono" value={fee} onChange={(e) => setFee(e.target.value)} inputMode="decimal" placeholder="0.01" />
            <small>The whole fee is the verifier's reward. The contract takes no cut.</small>
          </label>
        </div>
      </div>

      {localError && <div className="note bad">{localError}</div>}

      <div className="cta-row">
        <button className="btn primary" onClick={submit} disabled={!!busy || !wallet.address}>
          {busy ? "Working..." : `Request it for ${formatGen(feeWei, 3)} GEN`}
        </button>
      </div>
    </div>
  );
}
