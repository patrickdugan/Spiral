# Connector Calculus: errata to the frozen manuscript

**Applies to:** paper/manuscript.md at baseline a0a3140 (author line corrected per audit/ATTRIBUTION_CORRECTION.md)

**Why a separate file:** audit/validate_bundle.py and audit/inference/receipt.json bind manuscript.md by hash and reject any edit beyond the single author-line correction. The corrections below are therefore recorded here rather than applied in place. A future preregistered campaign that re-freezes the baseline should apply them at that point and re-bind.

## E1. Patent citation (References)

Replace:

> Rubio, Lihki, Dugan, and Pizarro. 2020. *Graph Re-write Using Ghost Nodes for Target Value Rebalancing*. U.S. Patent Application 16/920,416.

with:

> Dugan, Patrick B., Daniel P. Pizarro, and Lihki J. Rubio. *Graph Re-write Using Ghost Nodes for Target Value Rebalancing*. U.S. Patent Application Publication US 2021/0004796 A1, published January 7, 2021; application 16/920,416, filed July 2, 2020; claims priority to provisional 62/869,730, filed July 2, 2019.

Inventor order, publication number, publication date, and provisional data are from the USPTO Patent Public Search record. The 2020 date in the frozen entry is the filing year; the publication year is 2021.

## E2. In-text attribution (§1, §2.4, §7.7 and elsewhere)

Every occurrence of "[Rubio, Dugan, and Pizarro 2020]" should read "[Dugan, Pizarro, and Rubio 2021]".

## E3. Lineage statement (§2.4, first paragraph)

The frozen text reads:

> The earlier ghost-node work proposes graph rewrites for target-value rebalancing [Rubio, Dugan, and Pizarro 2020]. The recovered project did not retain the application text, so this paper does not reproduce or extend its claims. It adopts only the high-level construction: augment a graph with a nonphysical node or edge, solve a balancing problem in that augmented space, then map the result back to permissible operations.

Two corrections. The published application text is public, so the "did not retain" hedge no longer justifies the scope restriction; the restriction stands on its own terms and should be stated as a choice. And the application's subject is decentralized derivatives clearing, where ghost nodes connect and net subgraphs toward a target settlement value; it is not a rebalancing method for payment channels. Suggested replacement, keeping the paragraph's structure:

> The earlier ghost-node work, filed in a clearing setting, uses graph rewrites to connect and net derivative subgraphs toward a target settlement value [Dugan, Pizarro, and Rubio 2021]. This paper adopts only the high-level construction, augmenting a graph with a nonphysical node or edge, solving a balancing problem in that augmented space, and mapping the result back to permissible operations; the transplant from settlement netting to directional channel liquidity is made here and is not a claim of the application.

## E4. Environment paths

The frozen manuscript contains no drive-letter paths. The companion documents (liquidity_on_trial.md, connector_calculus_critique.md) have been corrected in place; audit/README.md and the historical receipts retain their original staging paths as provenance and are not edited.
