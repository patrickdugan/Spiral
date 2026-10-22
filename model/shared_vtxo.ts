/**
 * Two-holder Sapio/Ark shared-VTXO reference state machine.
 *
 * This is a deterministic adversarial model, NOT a Bitcoin consensus emulator,
 * a Sapio WASM evaluator, a proof of signing authority, or a production wallet.
 * The digest below detects altered fixture records; it is NOT a digital signature.
 *
 * For adversarial stale-branch tests, each prepared epoch is modeled as a
 * competing spend of the SAME parent outpoint. Actual Ark lineage and forfeits
 * must be inspected before applying a stale-branch result to an implementation.
 */
import { createHash } from "node:crypto";

export type PayoutMode = "separate" | "joint-2of2";
export type BundleReadiness = "complete" | "prepared" | "conditional";
export type ExitState =
  | "confirmed" | "already-confirmed" | "conflicted" | "incomplete"
  | "awaiting-ancestor" | "awaiting-maturity" | "awaiting-fees" | "expired";

export interface Entitlement {
  holder: string;
  script: string;
  sats: number;
}

export interface Payout {
  script: string;
  sats: number;
}

export interface RecoveryBundle {
  parentOutpoint: string;
  epoch: number;
  payoutMode: PayoutMode;
  outputs: Payout[];
  readiness: BundleReadiness;
  confirmedParentHeight: number;
  csvBlocks: number;
  expiryHeight: number;
  /** Synthetic fixture digest. No cryptographic signing is performed. */
  fixtureDigest: string;
}

export interface ExitResult {
  state: ExitState;
  payouts?: Payout[];
  epoch?: number;
  /** True if an obsolete, still-valid modeled recovery won the parent race. */
  staleWon?: boolean;
  feePaid?: number;
}

const safeSats = (n: number, label: string): void => {
  if (!Number.isSafeInteger(n) || n < 0) throw new RangeError(`${label} must be a nonnegative safe integer`);
};

const nonempty = (s: string, label: string): void => {
  if (typeof s !== "string" || s.length === 0) throw new TypeError(`${label} must be nonempty`);
};

const digest = (value: unknown): string =>
  createHash("sha256").update(JSON.stringify(value)).digest("hex");

const copyEntitlements = (rows: readonly Entitlement[]): Entitlement[] => rows.map(row => ({ ...row }));
const copyOutputs = (rows: readonly Payout[]): Payout[] => rows.map(row => ({ ...row }));

export function validateEntitlements(rows: readonly Entitlement[], backingSats: number): void {
  safeSats(backingSats, "backing");
  if (backingSats === 0 || rows.length < 2) throw new Error("shared parent requires positive backing and at least two holders");
  const owners = new Set<string>();
  const scripts = new Set<string>();
  let sum = 0;
  for (const row of rows) {
    nonempty(row.holder, "holder");
    nonempty(row.script, "beneficiary script");
    safeSats(row.sats, "share");
    if (row.sats === 0) throw new Error("zero-sized beneficiary");
    if (owners.has(row.holder)) throw new Error("duplicate holder");
    if (scripts.has(row.script)) throw new Error("separate beneficiary scripts must be unique");
    owners.add(row.holder);
    scripts.add(row.script);
    sum += row.sats;
    if (!Number.isSafeInteger(sum)) throw new RangeError("entitlement sum overflow");
  }
  if (sum !== backingSats) throw new Error(`entitlements ${sum} do not exhaust backing ${backingSats}`);
}

/** Native policy-envelope analogue: checks destinations but ignores their amounts. */
export function destinationAllowlistOnly(outputs: readonly Payout[], allowedScripts: ReadonlySet<string>): boolean {
  return outputs.length > 0 && outputs.every(o => allowedScripts.has(o.script));
}

/** Exact-value rule that an application-level shared ownership program must supply. */
export function exactEntitlementPolicy(outputs: readonly Payout[], owners: readonly Entitlement[]): boolean {
  if (outputs.length !== owners.length) return false;
  const expected = new Map(owners.map(o => [o.script, o.sats]));
  if (expected.size !== owners.length) return false;
  const seen = new Set<string>();
  for (const output of outputs) {
    if (!Number.isSafeInteger(output.sats) || output.sats <= 0) return false;
    if (seen.has(output.script) || expected.get(output.script) !== output.sats) return false;
    seen.add(output.script);
  }
  return true;
}

/** Recovery into one Bitcoin 2-of-2 output preserves a collective claim. */
export function canSpendPayout(
  mode: PayoutMode, signers: ReadonlySet<string>, beneficiaries: readonly Entitlement[], beneficiary?: string,
): boolean {
  if (mode === "separate") return beneficiary !== undefined
    && beneficiaries.some(row => row.holder === beneficiary) && signers.has(beneficiary);
  return beneficiaries.every(row => signers.has(row.holder));
}

interface EpochRecord {
  epoch: number;
  entitlements: Entitlement[];
  recovery: RecoveryBundle;
}

const bundleBody = (bundle: Omit<RecoveryBundle, "fixtureDigest">): Omit<RecoveryBundle, "fixtureDigest"> => ({
  parentOutpoint: bundle.parentOutpoint,
  epoch: bundle.epoch,
  payoutMode: bundle.payoutMode,
  outputs: copyOutputs(bundle.outputs),
  readiness: bundle.readiness,
  confirmedParentHeight: bundle.confirmedParentHeight,
  csvBlocks: bundle.csvBlocks,
  expiryHeight: bundle.expiryHeight,
});

function sealBundle(body: Omit<RecoveryBundle, "fixtureDigest">): RecoveryBundle {
  const normalized = bundleBody(body);
  return { ...normalized, fixtureDigest: digest(normalized) };
}

export class SharedVtxo {
  readonly parentOutpoint: string;
  readonly backingSats: number;
  readonly payoutMode: PayoutMode;
  readonly jointEscrowScript?: string;
  readonly confirmedParentHeight: number;
  readonly csvBlocks: number;
  readonly expiryHeight: number;
  readonly fixedRecoveryFee: number;
  private initial: Entitlement[];
  private epochs = new Map<number, EpochRecord>();
  private backups = new Map<string, Map<number, RecoveryBundle>>();
  private funded = false;
  private currentEpochNumber = 0;
  private winner: RecoveryBundle | undefined;
  private sapioOnline = true;
  private arkOnline = true;
  totalExternalFees = 0;

  constructor(config: {
    parentOutpoint: string;
    backingSats: number;
    entitlements: Entitlement[];
    payoutMode?: PayoutMode;
    jointEscrowScript?: string;
    confirmedParentHeight: number;
    csvBlocks: number;
    expiryHeight: number;
    fixedRecoveryFee: number;
  }) {
    nonempty(config.parentOutpoint, "parent outpoint");
    validateEntitlements(config.entitlements, config.backingSats);
    safeSats(config.confirmedParentHeight, "parent height");
    safeSats(config.csvBlocks, "CSV delay");
    safeSats(config.expiryHeight, "expiry height");
    safeSats(config.fixedRecoveryFee, "recovery fee");
    if (config.expiryHeight <= config.confirmedParentHeight + config.csvBlocks) {
      throw new Error("expiry must allow CSV maturity");
    }
    if (config.payoutMode === "joint-2of2") nonempty(config.jointEscrowScript ?? "", "joint escrow script");
    this.parentOutpoint = config.parentOutpoint;
    this.backingSats = config.backingSats;
    this.initial = copyEntitlements(config.entitlements);
    this.payoutMode = config.payoutMode ?? "separate";
    this.jointEscrowScript = config.jointEscrowScript;
    this.confirmedParentHeight = config.confirmedParentHeight;
    this.csvBlocks = config.csvBlocks;
    this.expiryHeight = config.expiryHeight;
    this.fixedRecoveryFee = config.fixedRecoveryFee;
  }

  get currentEpoch(): number { return this.currentEpochNumber; }
  get currentEntitlements(): Entitlement[] {
    return copyEntitlements(this.epochs.get(this.currentEpochNumber)?.entitlements ?? this.initial);
  }
  get confirmedRecovery(): RecoveryBundle | undefined {
    return this.winner && { ...this.winner, outputs: copyOutputs(this.winner.outputs) };
  }

  /** Flags stand in for services' ability to sign. No secret keys are modeled. */
  setOnline(service: "sapio" | "ark", online: boolean): void {
    if (service === "sapio") this.sapioOnline = online;
    else this.arkOnline = online;
  }

  private requireOnline(): void {
    if (!this.sapioOnline || !this.arkOnline) throw new Error("signers unavailable");
  }

  private makeRecovery(epoch: number, shares: readonly Entitlement[], readiness: BundleReadiness): RecoveryBundle {
    const outputs: Payout[] = this.payoutMode === "separate"
      ? shares.map(({ script, sats }) => ({ script, sats }))
      : [{ script: this.jointEscrowScript!, sats: this.backingSats }];
    if (this.payoutMode === "separate" && !exactEntitlementPolicy(outputs, shares)) {
      throw new Error("recovery breaks individual entitlements");
    }
    return sealBundle({
      parentOutpoint: this.parentOutpoint, epoch, payoutMode: this.payoutMode,
      outputs, readiness, confirmedParentHeight: this.confirmedParentHeight,
      csvBlocks: this.csvBlocks, expiryHeight: this.expiryHeight,
    });
  }

  /** Admission barrier: record the complete recovery before the modeled funding commitment. */
  fundWithPreparedRecovery(): RecoveryBundle {
    if (this.funded) throw new Error("already funded");
    this.requireOnline();
    const recovery = this.makeRecovery(0, this.initial, "complete");
    this.epochs.set(0, { epoch: 0, entitlements: copyEntitlements(this.initial), recovery });
    this.funded = true;
    return { ...recovery, outputs: copyOutputs(recovery.outputs) };
  }

  /** The debited owner must approve. Recipient scripts are immutable in this model. */
  transfer(from: string, to: string, sats: number, options: {
    approvals: readonly string[];
    nextRecovery?: BundleReadiness;
  }): RecoveryBundle {
    if (!this.funded) throw new Error("parent not funded");
    if (this.winner) throw new Error("parent already recovered");
    this.requireOnline();
    safeSats(sats, "transfer");
    if (sats === 0) throw new Error("zero transfer");
    if (!options.approvals.includes(from)) throw new Error("debit owner approval missing");
    const shares = this.currentEntitlements;
    const debit = shares.find(row => row.holder === from);
    const credit = shares.find(row => row.holder === to);
    if (!debit || !credit || debit === credit) throw new Error("unknown transfer parties");
    if (debit.sats <= sats) throw new Error("zero or negative remaining entitlement");
    debit.sats -= sats;
    credit.sats += sats;
    validateEntitlements(shares, this.backingSats);
    const next = this.currentEpochNumber + 1;
    const recovery = this.makeRecovery(next, shares, options.nextRecovery ?? "complete");
    // An unsigned or conditional successor never passes the commitment barrier.
    if (recovery.readiness !== "complete") throw new Error("successor recovery incomplete");
    this.epochs.set(next, { epoch: next, entitlements: shares, recovery });
    this.currentEpochNumber = next;
    return { ...recovery, outputs: copyOutputs(recovery.outputs) };
  }

  /** A beneficiary must preserve its own complete copy off-device. */
  backupFor(holder: string): RecoveryBundle {
    if (!this.funded) throw new Error("parent not funded");
    const rec = this.epochs.get(this.currentEpochNumber)!;
    if (!rec.entitlements.some(row => row.holder === holder)) throw new Error("unknown beneficiary");
    const copy = { ...rec.recovery, outputs: copyOutputs(rec.recovery.outputs) };
    if (!this.backups.has(holder)) this.backups.set(holder, new Map());
    this.backups.get(holder)!.set(rec.epoch, { ...copy, outputs: copyOutputs(copy.outputs) });
    return copy;
  }

  getBackup(holder: string, epoch = this.currentEpochNumber): RecoveryBundle | undefined {
    const bundle = this.backups.get(holder)?.get(epoch);
    return bundle && { ...bundle, outputs: copyOutputs(bundle.outputs) };
  }

  /** Validate exact fixture identity and the modeled epoch's persisted entitlement plan. */
  verifyBundle(bundle: RecoveryBundle): boolean {
    if (bundle.parentOutpoint !== this.parentOutpoint || bundle.payoutMode !== this.payoutMode) return false;
    const reference = this.epochs.get(bundle.epoch);
    if (!reference) return false;
    const body = bundleBody(bundle);
    return digest(body) === bundle.fixtureDigest && bundle.fixtureDigest === reference.recovery.fixtureDigest
      && reference.recovery.readiness === "complete";
  }

  /**
   * Simulated chain attempt. The first valid competing parent spend wins.
   * This deliberately does not use online signers or claim holder signatures:
   * the claimed Bitcoin transaction was already approved at admission.
   */
  attemptExit(bundle: RecoveryBundle, args: {
    height: number;
    externalFeeFunds: number;
    ancestorsAvailable?: boolean;
  }): ExitResult {
    safeSats(args.height, "exit height");
    safeSats(args.externalFeeFunds, "fee wallet funds");
    if (!this.verifyBundle(bundle)) return { state: "incomplete" };
    if (this.winner) {
      if (this.winner.fixtureDigest === bundle.fixtureDigest) return {
        state: "already-confirmed", payouts: copyOutputs(this.winner.outputs), epoch: this.winner.epoch, feePaid: 0,
      };
      return { state: "conflicted" };
    }
    if (args.ancestorsAvailable === false) return { state: "awaiting-ancestor" };
    if (args.height < this.confirmedParentHeight + this.csvBlocks) return { state: "awaiting-maturity" };
    // Worst-case conservative expiry cutoff in the model: a server may reclaim at expiry.
    if (args.height >= this.expiryHeight) return { state: "expired" };
    if (args.externalFeeFunds < this.fixedRecoveryFee) return { state: "awaiting-fees" };
    this.winner = { ...bundle, outputs: copyOutputs(bundle.outputs) };
    this.totalExternalFees += this.fixedRecoveryFee;
    return {
      state: "confirmed", epoch: bundle.epoch, payouts: copyOutputs(bundle.outputs),
      staleWon: bundle.epoch !== this.currentEpochNumber, feePaid: this.fixedRecoveryFee,
    };
  }
}

/**
 * Proof-carrying-registry accounting analogue. Assumes parent membership and
 * beneficiary ownership are externally authenticated. No ZK proof is executed.
 * A parent claim and its children are mutually exclusive eligibility units.
 */
export class ParentBackingRegistry {
  private records = new Map<string, {
    epoch: number;
    value: number;
    entitlements: Map<string, number>;
    childClaims: Map<string, number>;
    parentClaimed: boolean;
  }>();

  enroll(parentOutpoint: string, epoch: number, value: number, allocations: readonly Entitlement[]): void {
    nonempty(parentOutpoint, "parent");
    safeSats(epoch, "epoch");
    validateEntitlements(allocations, value);
    if (this.records.has(parentOutpoint)) throw new Error("backing outpoint already registered");
    this.records.set(parentOutpoint, {
      epoch, value, entitlements: new Map(allocations.map(x => [x.holder, x.sats])),
      childClaims: new Map(), parentClaimed: false,
    });
  }

  /** Epoch rolls only after an authenticated successor is accepted by the set maintainer. */
  rollEpoch(parentOutpoint: string, epoch: number, allocations: readonly Entitlement[]): void {
    const rec = this.records.get(parentOutpoint);
    if (!rec) throw new Error("unknown backing");
    if (epoch !== rec.epoch + 1) throw new Error("incorrect successor epoch");
    validateEntitlements(allocations, rec.value);
    rec.epoch = epoch;
    rec.entitlements = new Map(allocations.map(x => [x.holder, x.sats]));
    rec.childClaims.clear();
    rec.parentClaimed = false;
  }

  /** Multiple identities or subclaims cannot exceed the beneficiary's canonical share. */
  claimChild(parentOutpoint: string, epoch: number, holder: string, sats: number): void {
    const rec = this.records.get(parentOutpoint);
    if (!rec || rec.epoch !== epoch) throw new Error("unknown or stale claim epoch");
    if (rec.parentClaimed) throw new Error("parent already claimed");
    safeSats(sats, "child claim");
    if (sats === 0) throw new Error("zero child claim");
    const limit = rec.entitlements.get(holder);
    const current = rec.childClaims.get(holder) ?? 0;
    if (limit === undefined || current + sats > limit) throw new Error("claim exceeds canonical entitlement");
    rec.childClaims.set(holder, current + sats);
  }

  claimParent(parentOutpoint: string, epoch: number): void {
    const rec = this.records.get(parentOutpoint);
    if (!rec || rec.epoch !== epoch) throw new Error("unknown or stale claim epoch");
    if (rec.parentClaimed || rec.childClaims.size) throw new Error("parent backing already allocated");
    rec.parentClaimed = true;
  }

  totalEligibleWeight(): number {
    let n = 0;
    for (const rec of this.records.values()) {
      n += rec.parentClaimed ? rec.value : [...rec.childClaims.values()].reduce((a, b) => a + b, 0);
      if (!Number.isSafeInteger(n)) throw new RangeError("total eligible capital overflow");
    }
    return n;
  }
}
