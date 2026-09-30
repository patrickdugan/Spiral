// Extended settlement ledger: per-class holdings and clocked settlement events.
// Witnesses Proposition S1 of paper/where_the_capital_bound_moves.md on finite cases.
// Centralized reference semantics. Not a Lightning, Ark, or Bitcoin implementation.

export type ObjectClass = "U" | "C" | "V" | "E";

export type ClockCondition =
  | { kind: "confirmations"; required: number }
  | { kind: "htlc"; }                // settled when preimage revealed (explicit fire)
  | { kind: "csv"; blocks: number }  // relative timelock from initiation height
  | { kind: "round"; roundId: string }
  | { kind: "challenge"; delta: number; disproved?: boolean };

export interface SettlementEvent {
  id: string;
  from: { cls: ObjectClass; holder: string };
  to: { cls: ObjectClass; holder: string };
  amount: number;
  fee: number;            // paid to relay/miner, leaves the holder sum
  clock: ClockCondition;
  initiatedAt: number;    // block height
  state: "pending" | "settled" | "aborted";
}

export interface LedgerSnapshot {
  holdings: number;       // sum over classes and holders of settled holdings
  held: number;           // sum of pending holds (h)
  feesPaid: number;
  slashed: number;
  external: number;       // external funding in minus out
}

const key = (cls: ObjectClass, holder: string): string => `${cls}:${holder}`;

export class SettlementLedger {
  private readonly l = new Map<string, number>();
  private readonly h = new Map<string, number>();
  private readonly journal = new Map<string, SettlementEvent>();
  private readonly confirmedRounds = new Set<string>();
  private readonly settledHtlcs = new Set<string>();
  height = 0;
  feesPaid = 0;
  slashed = 0;
  external = 0;

  fund(cls: ObjectClass, holder: string, amount: number): void {
    if (!Number.isInteger(amount) || amount <= 0) throw new Error("amount must be a positive integer");
    const k = key(cls, holder);
    this.l.set(k, (this.l.get(k) ?? 0) + amount);
    this.external += amount;
  }

  balance(cls: ObjectClass, holder: string): number {
    return this.l.get(key(cls, holder)) ?? 0;
  }

  held(cls: ObjectClass, holder: string): number {
    return this.h.get(key(cls, holder)) ?? 0;
  }

  available(cls: ObjectClass, holder: string): number {
    return this.balance(cls, holder) - this.held(cls, holder);
  }

  /** Prepare a cross-class event: reserve amount+fee on the source, journal it, move nothing. */
  initiate(ev: Omit<SettlementEvent, "state" | "initiatedAt">): SettlementEvent {
    if (this.journal.has(ev.id)) throw new Error(`duplicate event id ${ev.id}`);
    if (!Number.isInteger(ev.amount) || ev.amount <= 0) throw new Error("amount must be a positive integer");
    if (!Number.isInteger(ev.fee) || ev.fee < 0) throw new Error("fee must be a nonnegative integer");
    const src = key(ev.from.cls, ev.from.holder);
    const need = ev.amount + ev.fee;
    if (this.available(ev.from.cls, ev.from.holder) < need) {
      throw new Error("insufficient available balance");
    }
    // All checks precede any mutation (L3 / S1 rejection identity).
    this.h.set(src, (this.h.get(src) ?? 0) + need);
    const rec: SettlementEvent = { ...ev, initiatedAt: this.height, state: "pending" };
    this.journal.set(ev.id, rec);
    return rec;
  }

  advance(blocks: number): void {
    this.height += blocks;
  }

  confirmRound(roundId: string): void {
    this.confirmedRounds.add(roundId);
  }

  settleHtlc(eventId: string): void {
    this.settledHtlcs.add(eventId);
  }

  /** Whether an event's clock condition has fired at the current height. */
  clockFired(ev: SettlementEvent): boolean {
    const c = ev.clock;
    switch (c.kind) {
      case "confirmations": return this.height - ev.initiatedAt >= c.required;
      case "csv": return this.height - ev.initiatedAt >= c.blocks;
      case "round": return this.confirmedRounds.has(c.roundId);
      case "htlc": return this.settledHtlcs.has(ev.id);
      case "challenge": return this.height - ev.initiatedAt >= c.delta;
    }
  }

  /** Settle: release the hold, debit the source, credit the destination, pay the fee. */
  settle(eventId: string): void {
    const ev = this.journal.get(eventId);
    if (!ev || ev.state !== "pending") throw new Error("not pending");
    if (!this.clockFired(ev)) throw new Error("clock has not fired");
    const src = key(ev.from.cls, ev.from.holder);
    const dst = key(ev.to.cls, ev.to.holder);
    const need = ev.amount + ev.fee;
    this.h.set(src, (this.h.get(src) ?? 0) - need);
    this.l.set(src, (this.l.get(src) ?? 0) - need);
    if (ev.clock.kind === "challenge" && ev.clock.disproved) {
      // An escrow release that was disproved settles as a slash: the amount leaves the holder sum.
      this.slashed += ev.amount;
    } else {
      this.l.set(dst, (this.l.get(dst) ?? 0) + ev.amount);
    }
    this.feesPaid += ev.fee;
    ev.state = "settled";
  }

  /** Abort: release the hold, move nothing. */
  abort(eventId: string): void {
    const ev = this.journal.get(eventId);
    if (!ev || ev.state !== "pending") throw new Error("not pending");
    const src = key(ev.from.cls, ev.from.holder);
    this.h.set(src, (this.h.get(src) ?? 0) - (ev.amount + ev.fee));
    ev.state = "aborted";
  }

  snapshot(): LedgerSnapshot {
    let holdings = 0;
    for (const v of this.l.values()) holdings += v;
    let held = 0;
    for (const v of this.h.values()) held += v;
    return { holdings, held, feesPaid: this.feesPaid, slashed: this.slashed, external: this.external };
  }

  pending(): SettlementEvent[] {
    return [...this.journal.values()].filter((e) => e.state === "pending");
  }
}

/** S1 identity at settled states: holdings + fees + slashed == external. */
export function conservationGap(s: LedgerSnapshot): number {
  return s.holdings + s.feesPaid + s.slashed - s.external;
}
