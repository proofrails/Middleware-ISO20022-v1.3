import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import solc from "solc";
import { ethers } from "ethers";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  // Read env
  // Normalize and validate env
  let rpcUrl = (process.env.RPC_URL || process.env.FLARE_RPC_URL || "").trim();
  let pk = (process.env.PRIVATE_KEY || process.env.ANCHOR_PRIVATE_KEY || "").trim();

  if (!rpcUrl) {
    throw new Error("Missing RPC_URL (or FLARE_RPC_URL) env");
  }
  if (!pk) {
    throw new Error("Missing PRIVATE_KEY (or ANCHOR_PRIVATE_KEY) env");
  }
  if (!pk.startsWith("0x")) {
    pk = "0x" + pk;
  }
  // Remove any stray whitespace characters
  pk = pk.replace(/\s+/g, "");
  if (!/^0x[0-9a-fA-F]{64}$/.test(pk)) {
    throw new Error("PRIVATE_KEY must be 0x-prefixed 32-byte hex");
  }

  // Load source
  const contractsDir = path.resolve(process.cwd(), "contracts");
  const solPath = path.join(contractsDir, "EvidenceAnchor.sol");
  const source = fs.readFileSync(solPath, "utf8");

  // Standard JSON input for solc
  const input = {
    language: "Solidity",
    sources: {
      "EvidenceAnchor.sol": { content: source },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          "*": ["abi", "evm.bytecode.object"],
        },
      },
    },
  };

  // Compile with solc
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  if (output.errors && output.errors.length) {
    const errs = output.errors.filter((e) => e.severity === "error");
    if (errs.length) {
      console.error("Solc errors:", errs);
      throw new Error("Compilation failed");
    }
  }

  const contractName = "EvidenceAnchor";
  const artifact = output.contracts["EvidenceAnchor.sol"][contractName];
  const abi = artifact.abi;
  const bytecode = artifact.evm.bytecode.object;

  if (!bytecode || bytecode.length === 0) {
    throw new Error("Empty bytecode. Compilation likely failed.");
  }

  // Persist ABI (overwrite to keep in sync)
  const abiPath = path.join(contractsDir, "EvidenceAnchor.abi.json");
  fs.writeFileSync(abiPath, JSON.stringify(abi, null, 2));

  // Deploy using ethers v6
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const wallet = new ethers.Wallet(pk, provider);

  console.log("Network RPC:", rpcUrl);
  console.log("Deployer:", wallet.address);

  const factory = new ethers.ContractFactory(abi, bytecode, wallet);
  const contract = await factory.deploy();
  console.log("Deployment tx:", contract.deploymentTransaction().hash);

  // Wait 1 confirmation
  await contract.deploymentTransaction().wait(1);
  const address = await contract.getAddress();

  // Fetch receipt/block
  const receipt = await provider.getTransactionReceipt(
    contract.deploymentTransaction().hash
  );
  const block = await provider.getBlock(receipt.blockNumber);

  // Save deployed metadata
  const deployedMeta = {
    contract: contractName,
    address,
    txHash: receipt.hash,
    blockNumber: receipt.blockNumber,
    timestamp: block?.timestamp || null,
    chainId: (await provider.getNetwork()).chainId.toString(),
  };
  const outPath = path.join(contractsDir, "EvidenceAnchor.deployed.json");
  fs.writeFileSync(outPath, JSON.stringify(deployedMeta, null, 2));

  console.log("Deployed address:", address);
  console.log("Saved:", outPath);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
