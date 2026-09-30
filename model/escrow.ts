// Optimistic escrow state machine in the BitVM3 Assert/Disprove/Withdraw pattern.
// Witnesses Proposition S4 on finite cases. Cost parameters are those published in ePrint 2026/933
// (Assert ≈ 2.4 kvB, Disprove ≈ 93 vB) and are inputs, not measurements. The "proof" is a boolean
// oracle standing in for garbled-circuit evaluation of a SNARK verifier; substituting the real
// evaluation changes nothing in the state machine.

export interface EscrowParams {
  delta: number;        // challenge period in blocks
  assertVb: number;     // Assert transaction size, vB
  disproveVb: number;   // Disprove transaction size, vB
  feeRate: number;      // sat/vB
}

export const BITVM3_PUBLISHED: Omit<EscrowParams, "delta" | "feeRate"> = { assertVb: 2400, disproveVb: 93 };

export type EscrowState = "locked" | "claimed" | "released" | "slashed";

export interface Costs { operatorFees: number; challengerFees: number; capitalBlocks: number; }

export class Escrow {
  readonly bond: number;
  readonly params: EscrowParams;
  state: EscrowState = "locked";
  private claimedAt = -1;
  private asserted: boolean | null = null;
  readonly costs: Costs = { operatorFees: 0, challengerFees: 0, capitalBlocks: 0 };
  private lockedSince = 0;

  constructor(bond: number, params: EscrowParams, lockedAt = 0) {
    if (!Number.isInteger(bond) || bond <= 0) throw new Error("bond must be a positive integer");
    this.bond = bond;
    this.params = params;
    this.lockedSince = lockedAt;
  }

  /** Operator asserts the release statement. `statementHolds` is what an honest evaluator would find. */
  assert(height: number, statementHolds: boolean): void {
    if (this.state !== "locked") throw new Error("not locked");
    this.state = "claimed";
    this.claimedAt = height;
    this.asserted = statementHolds;
    this.costs.operatorFees += this.params.assertVb * this.params.feeRate;
  }

  /** Any challenger may disprove during the period; succeeds iff the asserted statement is false. */
  disprove(height: number): boolean {
    if (this.state !== "claimed") return false;
    if (height - this.claimedAt >= this.params.delta) return false; // period over
    this.costs.challengerFees += this.params.disproveVb * this.params.feeRate;
    if (this.asserted === false) {
      this.state = "slashed";
      this.costs.capitalBlocks += this.bond * (height - this.lockedSince);
      return true;
    }
    return false; // a true assertion has no false-output label to reveal
  }

  /** Operator withdraws after the period if no disprove consumed the connector output. */
  withdraw(height: number): boolean {
    if (this.state !== "claimed") return false;
    if (height - this.claimedAt < this.params.delta) return false;
    this.state = "released";
    this.costs.capitalBlocks += this.bond * (height - this.lockedSince);
    return true;
  }
}

/** Honest-challenger requirement: with n challengers of which h are honest, the game is safe iff h ≥ 1. */
export const safeUnderChallengers = (honest: number): boolean => honest >= 1;
