import fs from "fs";
import path from "path";
import { ethers } from "ethers";

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    throw new Error("Usage: node scripts/anchor.js <bundleHashHex>");
  }
  let bundleHash = (args[0] || "").trim();
  if (!/^0x[0-9a-fA-F]{64}$/.test(bundleHash)) {
    throw new Error("bundleHash must be 0x-prefixed 32-byte hex");
  }

  // Env
  let rpcUrl = (process.env.RPC_URL || process.env.FLARE_RPC_URL || "").trim();
  let pk = (process.env.PRIVATE_KEY || process.env.ANCHOR_PRIVATE_KEY || "").trim();
  let addr = (process.env.CONTRACT_ADDR || process.env.ANCHOR_CONTRACT_ADDR || "").trim();

  if (!rpcUrl) throw new Error("Missing RPC_URL/FLARE_RPC_URL");
  if (!pk) throw new Error("Missing PRIVATE_KEY/ANCHOR_PRIVATE_KEY");
  if (!addr) throw new Error("Missing CONTRACT_ADDR/ANCHOR_CONTRACT_ADDR");
  if (!pk.startsWith("0x")) pk = "0x" + pk;
  pk = pk.replace(/\s+/g, "");
  if (!/^0x[0-9a-fA-F]{64}$/.test(pk)) throw new Error("PRIVATE_KEY must be 0x 32-byte hex");
  if (!/^0x[0-9a-fA-F]{40}$/.test(addr)) throw new Error("CONTRACT_ADDR must be 0x address");

  const abiPath = path.resolve(process.cwd(), "contracts", "EvidenceAnchor.abi.json");
  const abi = JSON.parse(fs.readFileSync(abiPath, "utf8"));

  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const wallet = new ethers.Wallet(pk, provider);
  const contract = new ethers.Contract(addr, abi, wallet);

  // Call anchorEvidence(bytes32)
  const hashBytes = ethers.getBytes(bundleHash);
  if (hashBytes.length !== 32) throw new Error("bundleHash must be 32 bytes");

  const tx = await contract.anchorEvidence(hashBytes);
  const receipt = await tx.wait(1);

  const out = {
    txid: tx.hash,
    blockNumber: receipt?.blockNumber ?? null
  };
  // Print JSON result on stdout
  console.log(JSON.stringify(out));
}

main().catch((e) => {
  console.error(e?.message || String(e));
  process.exit(1);
});
