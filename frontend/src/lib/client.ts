import { createClient } from "genlayer-js";
import { CHAIN, CHAIN_ID_HEX, CHAIN_NAME, RPC_URL } from "../config";

interface EthereumProvider {
  isMetaMask?: boolean;
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on: (event: string, handler: (...args: unknown[]) => void) => void;
  removeListener: (event: string, handler: (...args: unknown[]) => void) => void;
}

declare global {
  interface Window {
    ethereum?: EthereumProvider;
  }
}

/** A genlayer-js client. With `address` it signs through window.ethereum. */
export function createVPClient(address?: string | null) {
  const config: Record<string, unknown> = { chain: CHAIN };
  if (address) config.account = address as `0x${string}`;
  if (RPC_URL) config.endpoint = RPC_URL;
  return createClient(config as any) as any;
}

export function getProvider(): EthereumProvider | null {
  if (typeof window === "undefined") return null;
  return window.ethereum || null;
}

export function hasEthereumProvider(): boolean {
  return !!getProvider();
}

export async function requestAccounts(): Promise<string[]> {
  const provider = getProvider();
  if (!provider) throw new Error("No injected wallet found. Install MetaMask.");
  return (await provider.request({ method: "eth_requestAccounts" })) as string[];
}

export async function getAccounts(): Promise<string[]> {
  const provider = getProvider();
  if (!provider) return [];
  try {
    return (await provider.request({ method: "eth_accounts" })) as string[];
  } catch {
    return [];
  }
}

export async function getBalance(address: string): Promise<bigint> {
  const provider = getProvider();
  if (!provider) return 0n;
  try {
    const result = await provider.request({ method: "eth_getBalance", params: [address, "latest"] });
    return BigInt(result as string);
  } catch {
    return 0n;
  }
}

export async function getChainId(): Promise<string | null> {
  const provider = getProvider();
  if (!provider) return null;
  try {
    return ((await provider.request({ method: "eth_chainId" })) as string) ?? null;
  } catch {
    return null;
  }
}

export async function connectWallet(): Promise<string> {
  const accounts = await requestAccounts();
  if (!accounts.length) throw new Error("The wallet returned no accounts.");
  return accounts[0];
}

export function onAccountsChanged(handler: (accounts: string[]) => void): () => void {
  const provider = getProvider();
  if (!provider) return () => undefined;
  const wrapped = (accounts: unknown) => handler(accounts as string[]);
  provider.on("accountsChanged", wrapped);
  return () => provider.removeListener("accountsChanged", wrapped);
}

export function onChainChanged(handler: (chainId: string) => void): () => void {
  const provider = getProvider();
  if (!provider) return () => undefined;
  const wrapped = (id: unknown) => handler(id as string);
  provider.on("chainChanged", wrapped);
  return () => provider.removeListener("chainChanged", wrapped);
}

/** Ask the wallet to add or switch to the chain the SDK is actually using. */
export async function switchToChain(): Promise<void> {
  const provider = getProvider();
  if (!provider) throw new Error("No injected wallet found.");
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: CHAIN_ID_HEX }],
    });
  } catch (e: any) {
    // 4902: the wallet has never seen this chain, so offer to add it
    if (e?.code === 4902) {
      await provider.request({
        method: "wallet_addEthereumChain",
        params: [
          {
            chainId: CHAIN_ID_HEX,
            chainName: CHAIN_NAME,
            rpcUrls: [RPC_URL],
            nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 },
          },
        ],
      });
      return;
    }
    throw e;
  }
}
