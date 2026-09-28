import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { createVPClient } from "../lib/client";
import { VisualProof } from "../lib/contract";
import { AttestationSummary, Stats } from "../lib/types";
import { describeError } from "../lib/errors";
import { isConfigured } from "../config";
import { useWallet } from "../hooks/useWallet";

const EMPTY_STATS: Stats = {
  attestations: 0,
  attested: 0,
  confirmed: 0,
  refuted: 0,
  challenged: 0,
  overturned: 0,
  voidRounds: 0,
  held: 0n,
  rewarded: 0n,
  refunded: 0n,
  bondsHeld: 0n,
  bondPayouts: 0n,
};

interface Ctx {
  wallet: ReturnType<typeof useWallet>;
  read: VisualProof;
  attestations: AttestationSummary[];
  stats: Stats;
  loading: boolean;
  error: string | null;
  busy: string | null;
  txError: string | null;
  lastTx: string | null;
  version: number;
  refresh: () => void;
  dismissTx: () => void;
  run: (label: string, fn: (c: VisualProof) => Promise<string>) => Promise<boolean>;
}

const VisualProofCtx = createContext<Ctx | null>(null);

export function VisualProofProvider({ children }: { children: ReactNode }) {
  const wallet = useWallet();
  const [attestations, setAttestations] = useState<AttestationSummary[]>([]);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [txError, setTxError] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const readClient = useMemo(() => new VisualProof(createVPClient()), []);
  const writeClient = useMemo(() => new VisualProof(createVPClient(wallet.address)), [wallet.address]);

  const load = useCallback(async () => {
    if (!isConfigured()) {
      setLoading(false);
      setError("No contract address is configured for this deployment.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [list, s] = await Promise.all([
        readClient.listAttestations(0, 50, false),
        readClient.getStats(),
      ]);
      setAttestations(list);
      setStats(s);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, [readClient]);

  useEffect(() => {
    load();
  }, [load, version]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const run = useCallback(
    async (label: string, fn: (c: VisualProof) => Promise<string>) => {
      setBusy(label);
      setTxError(null);
      setLastTx(null);
      try {
        const txHash = await fn(writeClient);
        await writeClient.waitForReceipt(txHash);
        setLastTx(txHash);
        refresh();
        return true;
      } catch (e) {
        setTxError(describeError(e));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [writeClient, refresh],
  );

  const dismissTx = useCallback(() => setTxError(null), []);

  const value: Ctx = {
    wallet,
    read: readClient,
    attestations,
    stats,
    loading,
    error,
    busy,
    txError,
    lastTx,
    version,
    refresh,
    dismissTx,
    run,
  };

  return <VisualProofCtx.Provider value={value}>{children}</VisualProofCtx.Provider>;
}

export function useVisualProof(): Ctx {
  const ctx = useContext(VisualProofCtx);
  if (!ctx) throw new Error("useVisualProof must be used inside VisualProofProvider");
  return ctx;
}
