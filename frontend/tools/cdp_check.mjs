// Boots the built app in a real Chrome over CDP and reports what rendered.
//
//   node tools/cdp_check.mjs http://localhost:4183/
//
// Run it against `vite preview` to prove the production bundle boots and
// renders, and against the deployed URL to prove the live contract reads.
// A typecheck says the code compiles; this says the app actually came up.
// Requires a Chrome with --remote-debugging-port=9222 already running.
const CDP = "http://127.0.0.1:9222";
const URL_TO_LOAD = process.argv[2] || "http://127.0.0.1:4183/";

async function main() {
  const created = await fetch(`${CDP}/json/new?${encodeURIComponent(URL_TO_LOAD)}`, { method: "PUT" });
  const target = await created.json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const msgId = ++id;
      pending.set(msgId, { resolve, reject });
      ws.send(JSON.stringify({ id: msgId, method, params }));
    });

  const consoleErrors = [];
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
  // give the module graph and the first contract read time to settle
  await new Promise((r) => setTimeout(r, 7000));

  const probe = await send("Runtime.evaluate", {
    expression: `JSON.stringify({
      title: document.title,
      url: location.href,
      hash: location.hash,
      rootChildren: document.getElementById('root') ? document.getElementById('root').children.length : null,
      text: document.getElementById('root') ? document.getElementById('root').innerText.slice(0, 1200) : null
    })`,
    returnByValue: true,
  });
  console.log("PAGE " + probe.result.value);
  console.log("CONSOLE_ERRORS " + JSON.stringify(consoleErrors));
  await fetch(`${CDP}/json/close/${target.id}`);
  ws.close();
}

main().catch((e) => {
  console.log("CDP_FAILURE " + e.message);
  process.exit(1);
});
