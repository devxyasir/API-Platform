// AES-256-GCM payload envelope — the browser half of the server's app/auth/envelope.py.
//
// The server hands us a per-session key (`enc_key`, standard base64) at login. When we send
// `X-Enc: 1` on an /account request, the request body must be the url-safe base64 (no padding) of
//   nonce(12) || ciphertext || GCM-tag(16)
// and the server returns its response body in the same envelope (marked `X-Enc: 1`).
//
// This is obfuscation layered on top of TLS + server-side RBAC — NOT the access boundary.
// It keeps dashboard JSON out of the Network tab as readable text; authorization is always
// enforced server-side, so a user who decrypts their own traffic still cannot reach anything
// their token isn't scoped for.

const NONCE_BYTES = 12;

// importKey is mildly expensive; cache the CryptoKey for the current key string.
let cached: { b64: string; key: CryptoKey } | null = null;

function hasSubtle(): boolean {
  return (
    typeof globalThis !== "undefined" &&
    !!globalThis.crypto?.subtle &&
    typeof globalThis.crypto.getRandomValues === "function"
  );
}

// True when envelope crypto can actually run in this environment.
export function cryptoAvailable(): boolean {
  return hasSubtle();
}

// Decode base64 (standard OR url-safe, padded or not) to bytes.
function b64ToBytes(input: string): Uint8Array {
  let s = input.trim().replace(/-/g, "+").replace(/_/g, "/");
  s += "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// Encode bytes to url-safe base64 WITHOUT padding (the server re-pads on decode).
function bytesToB64Url(bytes: Uint8Array): string {
  let bin = "";
  const CHUNK = 0x8000; // chunk to stay under the argument-count limit of fromCharCode
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function importKey(encKeyB64: string): Promise<CryptoKey | null> {
  if (!hasSubtle()) return null;
  if (cached && cached.b64 === encKeyB64) return cached.key;
  try {
    const raw = b64ToBytes(encKeyB64);
    const key = await crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, [
      "encrypt",
      "decrypt",
    ]);
    cached = { b64: encKeyB64, key };
    return key;
  } catch {
    return null;
  }
}

// Encrypt a plaintext string (JSON) → url-safe base64 envelope. Returns null if crypto is
// unavailable or the key can't be imported (caller falls back to plaintext).
export async function encryptEnvelope(
  encKeyB64: string,
  plaintext: string,
): Promise<string | null> {
  const key = await importKey(encKeyB64);
  if (!key) return null;
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_BYTES));
  const data = new TextEncoder().encode(plaintext);
  const ctBuf = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, data);
  const ct = new Uint8Array(ctBuf);
  const out = new Uint8Array(nonce.length + ct.length);
  out.set(nonce, 0);
  out.set(ct, nonce.length);
  return bytesToB64Url(out);
}

// Decrypt a url-safe base64 envelope → plaintext string. Throws on tamper / short input.
export async function decryptEnvelope(encKeyB64: string, token: string): Promise<string> {
  const key = await importKey(encKeyB64);
  if (!key) throw new Error("crypto unavailable");
  const raw = b64ToBytes(token);
  if (raw.length <= NONCE_BYTES) throw new Error("ciphertext too short");
  const nonce = raw.subarray(0, NONCE_BYTES);
  const ct = raw.subarray(NONCE_BYTES);
  const ptBuf = await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ct);
  return new TextDecoder().decode(ptBuf);
}
