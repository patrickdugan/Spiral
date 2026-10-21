// Exact satoshi fee arithmetic from Bark 8f5d8c4... lib/src/fees.rs and the
// executed captaind.toml. These are pricing rules, not externally lost value.
import { integer, sum } from "./capital.ts";
export interface FeeInput { amount: number; expiry: number }
export const EXPIRY_PPM = [[0, 0], [97, 1000], [199, 4000], [2161, 8000]] as const;
const ceilPpm = (numerator: bigint): number => integer(Number((numerator + 999999n) / 1000000n));
export function expiryFee(inputs: FeeInput[], height: number, chargeable?: number): number {
  integer(height); if (chargeable !== undefined) integer(chargeable);
  const buckets = EXPIRY_PPM.map(() => 0);
  for (const input of inputs) {
    integer(input.amount); integer(input.expiry);
    const remaining = Math.max(0, input.expiry - height);
    let index = EXPIRY_PPM.length - 1;
    while (remaining < EXPIRY_PPM[index][0]) index--;
    buckets[index] = integer(buckets[index] + input.amount);
  }
  let remaining = chargeable ?? sum(inputs.map(x => x.amount)), numerator = 0n;
  for (let i = 0; i < buckets.length; i++) {
    const take = Math.min(remaining, buckets[i]); remaining -= take;
    numerator += BigInt(take) * BigInt(EXPIRY_PPM[i][1]);
  }
  return ceilPpm(numerator);
}
export const boardFee = (amount: number) => Math.max(330, 100 + ceilPpm(BigInt(integer(amount)) * 1000n));
export const receiveFee = (amount: number) => 100 + ceilPpm(BigInt(integer(amount)) * 2000n);
export const refreshFee = (inputs: FeeInput[], height: number) => 150 + expiryFee(inputs, height);
export const sendFee = (amount: number, inputs: FeeInput[], height: number) => Math.max(10, 75 + expiryFee(inputs, height, integer(amount)));
export const routingLimit = (holderFee: number) => integer(Number(BigInt(integer(holderFee)) * 900000n / 1000000n));

// Observed single-participant transaction shape, not a fee estimator for a
// larger batched tree. The final forecast must name this batching assumption.
export const OBSERVED_TRANSACTION_COSTS = Object.freeze({ roundMiner: 3857, rootOverhead: 330, boardMiner: 155,
  boardSweepMiner: 1295, channelOpenMiner: 166, outboundBuffer: 9306, inboundBuffer: 5000 });
