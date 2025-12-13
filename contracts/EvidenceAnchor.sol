// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract EvidenceAnchor {
    event EvidenceAnchored(bytes32 bundleHash, address indexed sender, uint256 ts);

    function anchorEvidence(bytes32 bundleHash) external {
        emit EvidenceAnchored(bundleHash, msg.sender, block.timestamp);
    }
}
