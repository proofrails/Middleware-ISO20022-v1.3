import fs from "fs";
import path from "path";
import { ethers } from "ethers";

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    throw new Error("Usage: node scripts/find.js <bundleHashHex>");
  }
  let bundleHash = (args[0] || "").trim();
  if (!/^0x[0-9a-fA-F]{64}$/.test(bundleHash)) {
    throw new Error("bundleHash must be 0x-prefixed 32-byte hex");
  }

  // Env
  let rpcUrl = (process.env.RPC_URL || process.env.FLARE_RPC_URL || "").trim();
  let addr = (process.env.CONTRACT_ADDR || process.env.ANCHOR_CONTRACT_ADDR || "").trim();

  if (!rpcUrl) throw new Error("Missing RPC_URL/FLARE_RPC_URL");
  if (!addr) throw new Error("Missing CONTRACT_ADDR/ANCHOR_CONTRACT_ADDR");
  if (!/^0x[0-9a-fA-F]{40}$/.test(addr)) throw new Error("CONTRACT_ADDR must be 0x address");

  const abiPath = path.resolve(process.cwd(), "contracts", "EvidenceAnchor.abi.json");
  const abi = JSON.parse(fs.readFileSync(abiPath, "utf8"));

  const provider = new ethers.JsonRpcProvider(rpcUrl);

  // Interface and event topic
  const iface = new ethers.Interface(abi);
  const eventFrag = iface.getEvent("EvidenceAnchored");
  const topic0 = iface.getEventTopic(eventFrag);

  // Look back a window of blocks
  const latest = await provider.getBlockNumber();
  const LOOKBACK = parseInt(process.env.ANCHOR_LOOKBACK_BLOCKS || "50000", 10);
  const fromBlock = Math.max(0, latest - LOOKBACK);

  // Fetch logs filtered by event signature only (bundleHash is not indexed)
  const logs = await provider.getLogs({
    address: addr,
    fromBlock,
    toBlock: latest,
    topics: [topic0],
  });

  // Decode and compare bundleHash
  for (let i = logs.length - 1; i >= 0; i--) {
    const log = logs[i];
    try {
      const parsed = iface.parseLog(log);
      const evHash = parsed.args?.bundleHash;
      // evHash may be a BytesLike; convert to hex
      const evHex = ethers.hexlify(evHash);
      if (evHex.toLowerCase() === bundleHash.toLowerCase()) {
        const tx = await provider.getTransaction(log.transactionHash);
        const blk = await provider.getBlock(log.blockNumber);
        const out = {
          matches: true,
          txid: log.transactionHash,
          anchored_at: blk?.timestamp ? new Date(blk.timestamp * 1000).toISOString() : null,
        };
        console.log(JSON.stringify(out));
        return;
      }
    } catch {
      // skip decode errors
    }
  }

  console.log(JSON.stringify({ matches: false }));
}

main().catch((e) => {
  console.error(e?.message || String(e));
  process.exit(1);
});
