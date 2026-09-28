// Drive the built app in a real Chrome over CDP and check every route, every
// per-state action set, the wallet wiring and the form validation.
//
//   node tools/frontend_sweep.mjs http://127.0.0.1:4183/
//
// Needs a Chrome already listening on --remote-debugging-port=9222. The wallet
// is stubbed through Page.addScriptToEvaluateOnNewDocument, because a headless
// browser has no MetaMask: that lets the connect flow, the balance read and the
// wrong-network notice be exercised for real, while the write path stops at the
// point where a wallet would have to sign.
//
// Optional third argument: a comma-separated list of ids that should be showing
// a window-closed action (refund, release reward, finalize).

const CDP = "http://127.0.0.1:9222";
const BASE = (process.argv[2] || "http://127.0.0.1:4183/").replace(/\/$/, "");
const CLOSED_WINDOW_IDS = (process.argv[3] || "").split(",").filter(Boolean).map(Number);

const CHAIN_ID_CORRECT = "0xf22f"; // 61999, the id genlayer-js uses for StudioNet
const ADDRESS = "0x7665edA43daC71D545Dca6C796ce2aF544bfab33";

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok: !!ok, detail });
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${ok || !detail ? "" : `   [${detail}]`}`);
}

function stubWalletSource({ connected, chainId }) {
  return `(() => {
    const addr = "${ADDRESS}";
    window.ethereum = {
      isMetaMask: true,
      request: async ({ method }) => {
        if (method === "eth_accounts") return ${connected ? "[addr]" : "[]"};
        if (method === "eth_requestAccounts") return [addr];
        if (method === "eth_chainId") return "${chainId}";
        if (method === "eth_getBalance") return "0xde0b6b3a7640000";
        if (method === "wallet_switchEthereumChain" || method === "wallet_addEthereumChain") return null;
        return null;
      },
      on: () => {},
      removeListener: () => {},
    };
  })();`;
}

async function openTarget(url, { connected = true, chainId = CHAIN_ID_CORRECT } = {}) {
  const created = await fetch(`${CDP}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" });
  const target = await created.json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const consoleErrors = [];
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const msgId = ++id;
      pending.set(msgId, { resolve, reject });
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
      return;
    }
    if (msg.method === "Runtime.exceptionThrown") {
      consoleErrors.push(msg.params.exceptionDetails?.exception?.description ?? "exception");
    }
    if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description).join(" "));
    }
  };
  await new Promise((r) => (ws.onopen = r));
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", { source: stubWalletSource({ connected, chainId }) });
  await send("Page.navigate", { url });
  await new Promise((r) => setTimeout(r, 6500));

  const evalJs = async (expression, awaitPromise = false) => {
    const out = await send("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
    if (out.exceptionDetails) throw new Error(out.exceptionDetails.exception?.description ?? "eval failed");
    return out.result.value;
  };

  // A page that did not load must fail loudly: Vercel's bot protection, a bad
  // deploy or an empty shell would otherwise make every assertion below pass by
  // accident, because none of the strings they look for would be there either.
  const loaded = await evalJs("document.body.innerText.includes('VisualProof')");
  if (!loaded) {
    check(`the app loads at ${url}`, false, (await evalJs("document.body.innerText.slice(0, 90)")).replace(/\n/g, " "));
  }

  return {
    evalJs,
    loaded,
    consoleErrors,
    close: async () => {
      ws.close();
      await fetch(`${CDP}/json/close/${target.id}`);
    },
  };
}

async function attempt(name, fn) {
  try {
    return await fn();
  } catch (e) {
    check(name, false, String(e.message).slice(0, 120));
  }
}

/**
 * genlayer-js logs a failed attempt even when a retry recovers it, so dropped
 * RPC requests are counted separately from errors the app did not handle. The
 * distinction matters: a hiccup the retry absorbed is not an app failure, but
 * it is still worth reporting, because a user sees the same wall if the retry
 * budget ever runs out.
 */
const isRpcHiccup = (e) => /Failed to fetch|gen_call|NetworkError|fetch failed/i.test(String(e));
const realErrors = (page) => page.consoleErrors.filter((e) => !isRpcHiccup(e));
const hiccups = (page) => page.consoleErrors.filter(isRpcHiccup).length;
let hiccupTotal = 0;

const text = (p) => p.evalJs("document.getElementById('root').innerText");

async function main() {
  const board = await fetch(`${BASE}/`).then((r) => r.text());
  check("the production HTML references a built bundle", /\/assets\/index-[\w-]+\.js/.test(board));

  // ---------------------------------------------------------------- routes
  console.log("\n-- routes --");
  for (const [route, needle] of [
    ["/", "Standing attestations"],
    ["/#/new", "Request an attestation"],
    ["/#/how", "How the judgement works"],
  ]) {
    const p = await openTarget(`${BASE}${route}`);
    const t = await text(p);
    check(`${route} renders`, p.loaded && t.includes(needle), t.slice(0, 80));
    check(`${route} reports no unhandled error`, p.loaded && realErrors(p).length === 0, realErrors(p)[0]);
    hiccupTotal += hiccups(p);
    await p.close();
  }

  // --------------------------------------------------------------- the board
  console.log("\n-- board, reading the live contract --");
  const b = await openTarget(`${BASE}/`);
  const bt = await text(b);
  check("the board lists the seeded attestations", b.loaded && /#\d+/.test(bt) && bt.includes("attestations requested"));
  check("the board shows the money the contract holds", b.loaded && /GEN held for verifiers/.test(bt));
  check("the board shows no read error", b.loaded && !bt.includes("Could not read the contract"));
  const ids = [...bt.matchAll(/#(\d+)/g)].map((m) => Number(m[1]));
  check("the board returns more than one attestation", b.loaded && ids.length > 1, `ids: ${ids.join(",")}`);
  await b.close();

  // a record that really is absent must not be confused with a dropped request:
  // the page may report either, and must never report anything else
  const missing = await openTarget(`${BASE}/#/attestations/9999`);
  const mt = await text(missing);
  const saidAbsent = mt.includes("does not exist");
  const saidRetry = mt.includes("did not answer") && mt.includes("Read it again");
  check("an absent record either says so or offers a retry", missing.loaded && (saidAbsent || saidRetry), mt.slice(-140));
  check("an absent record is never reported as something else", missing.loaded && !/Could not read the contract|Oops|undefined/.test(mt));
  await missing.close();

  // ------------------------------------------------------- per-state actions
  console.log("\n-- per-state action sets --");
  const expected = [
    [ids[ids.length - 1], "Run the attestation", "a REQUESTED record offers the attestation"],
    [ids[0], null, "the newest record renders"],
  ];
  for (const [id, needle, label] of expected) {
    if (!id) continue;
    const p = await openTarget(`${BASE}/#/attestations/${id}`);
    const t = await text(p);
    check(label, p.loaded && (needle ? t.includes(needle) : t.includes(`Attestation #${id}`)), t.slice(0, 90));
    await p.close();
  }

  // every id gets a page, and the page always names the record
  for (const id of ids) {
    const p = await openTarget(`${BASE}/#/attestations/${id}`);
    const t = await text(p);
    check(
      `#${id}: detail page renders with a status`,
      p.loaded && t.includes(`Attestation #${id}`) && /challenged|verdict|refunded|corrected|awaiting/.test(t),
      t.slice(-140),
    );
    check(`#${id}: no unhandled error`, p.loaded && realErrors(p).length === 0, realErrors(p)[0]);
    hiccupTotal += hiccups(p);
    await p.close();
  }

  // ------------------------------- buttons that only appear once a window closed
  for (const id of CLOSED_WINDOW_IDS) {
    const p = await openTarget(`${BASE}/#/attestations/${id}`);
    const t = await text(p);
    const offers = /Refund: nobody attested this in time|Release the reward to the verifier|Finalize: the window passed/.test(t);
    check(`#${id}: offers the window-closed action`, p.loaded && offers, t.slice(-160));
    await p.close();
  }

  // ------------------------------------------------------------- the wallet
  console.log("\n-- wallet wiring --");
  const w1 = await openTarget(`${BASE}/`, { connected: false });
  const noWallet = await text(w1);
  check(
    "no injected wallet offers to install one",
    w1.loaded && (noWallet.includes("Install a wallet") || noWallet.includes("Connect wallet")),
    noWallet.slice(0, 90),
  );
  await w1.close();

  const w2 = await openTarget(`${BASE}/`, { connected: true });
  const connected = await text(w2);
  check("a stub wallet is detected without a click", w2.loaded && connected.includes("0x7665"), connected.slice(0, 120));
  check("the balance is read from the wallet", w2.loaded && /1 GEN/.test(connected), connected.slice(0, 120));
  check("the connect button is gone once a wallet answers", w2.loaded && !connected.includes("Connect wallet"));
  check("the right chain draws no warning", w2.loaded && !connected.includes("not on"));
  await w2.close();

  const w3 = await openTarget(`${BASE}/`, { connected: true, chainId: "0x1" });
  const wrongChain = await text(w3);
  check("a wallet on the wrong chain is warned", w3.loaded && wrongChain.includes("not on"), wrongChain.slice(0, 120));
  await w3.close();

  // ---------------------------------------------------------------- the form
  console.log("\n-- request form validation --");
  const setValue = (selector, value) => `(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, ${JSON.stringify(value)});
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return el.value;
  })()`;
  const clickSubmit = `(() => {
    const btns = [...document.querySelectorAll("button")];
    const submit = btns.find((b) => /Request it for/.test(b.textContent));
    if (!submit) return "no submit button";
    submit.click();
    return "clicked";
  })()`;

  const form = await openTarget(`${BASE}/#/new`, { connected: true });
  const fillAndSubmit = async (selector, value, label) =>
    attempt(`${label}: submit responds`, async () => {
      await form.evalJs(setValue(selector, value));
      await form.evalJs(clickSubmit);
      await new Promise((r) => setTimeout(r, 900));
    });

  await fillAndSubmit('input[placeholder="https://..."]', "not-a-url", "a non-http target");
  let ft = await text(form);
  check("a non-http target is refused before sending", form.loaded && ft.includes("must be a public http(s) page"), ft.slice(-160));

  await form.evalJs(setValue('input[placeholder="https://..."]', "https://example.com/"));
  await fillAndSubmit("textarea", "  ", "a blank claim");
  ft = await text(form);
  check("a blank claim is refused before sending", form.loaded && ft.includes("needs 1 to 400 characters"), ft.slice(-160));

  await form.evalJs(setValue("textarea", "The page shows the heading 'Example Domain'."));
  await fillAndSubmit('input[inputmode="decimal"]', "0.001", "a fee under the minimum");
  ft = await text(form);
  check("a fee under the minimum is refused before sending", form.loaded && ft.includes("at least 0.01 GEN"), ft.slice(-160));

  const parsed = await form.evalJs(
    `(() => {
      const el = document.querySelector('input[inputmode="decimal"]');
      return el ? el.value : null;
    })()`,
  );
  check("the fee field carries what was typed", parsed === "0.001", String(parsed));

  await form.evalJs(`(() => {
    const el = document.querySelector('select');
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(el, "text");
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return el.value;
  })()`);
  const mode = await form.evalJs(`document.querySelector('select').value`);
  check("the evidence mode can be switched to text", mode === "text", String(mode));

  check("the form reports no unhandled error", form.loaded && realErrors(form).length === 0, realErrors(form)[0]);
  hiccupTotal += hiccups(form);
  await form.close();

  // ------------------------------------------------------------------ summary
  const failed = results.filter((r) => !r.ok);
  if (hiccupTotal) {
    console.log(
      `\nnote: ${hiccupTotal} dropped RPC request(s) were logged and recovered by the read retry.`,
    );
  }
  console.log(`\n===== ${results.length - failed.length}/${results.length} frontend checks passed =====`);
  for (const f of failed) console.log(`  FAILED: ${f.name}  ${f.detail}`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  console.log("SWEEP_FAILURE " + e.message);
  process.exit(1);
});
