import { test } from "node:test";
import assert from "node:assert/strict";
import { boardFee, receiveFee, refreshFee, sendFee, routingLimit, expiryFee } from "./capital-fees.ts";

test("pinned fee arithmetic reproduces all observed holder fees", () => {
  assert.equal(boardFee(100000), 330);
  assert.equal(sendFee(60000, [{ amount: 99670, expiry: 4433 }], 116), 555);
  assert.equal(routingLimit(555), 499);
  assert.equal(refreshFee([{ amount: 39115, expiry: 4433 }], 1000), 463);
  assert.equal(refreshFee([{ amount: 38652, expiry: 5320 }], 4436), 305);
});
test("expiry thresholds are inclusive and fees round once across input buckets", () => {
  for (const [expiry, fee] of [[96, 0], [97, 1], [198, 1], [199, 4], [2160, 4], [2161, 8]])
    assert.equal(expiryFee([{ amount: 1000, expiry }], 0), fee);
  assert.equal(expiryFee([{ amount: 500, expiry: 97 }, { amount: 500, expiry: 97 }], 0), 1);
  assert.equal(expiryFee([{ amount: 1, expiry: 97 }, { amount: 1, expiry: 2161 }], 0), 1);
  assert.equal(receiveFee(10500), 121);
});
test("payment fee charges soonest-expiring buckets first, independent of input order", () => {
  const inputs = [{ amount: 10000, expiry: 4320 }, { amount: 10000, expiry: 50 }];
  assert.equal(sendFee(12000, inputs, 0), 91);
  assert.equal(sendFee(12000, [...inputs].reverse(), 0), 91);
  assert.equal(refreshFee(inputs, 0), 230);
});
test("fee arithmetic rejects invalid monetary and height inputs", () => {
  assert.throws(() => boardFee(-1)); assert.throws(() => receiveFee(.5));
  assert.throws(() => expiryFee([{ amount: 100, expiry: -1 }], 0));
  assert.throws(() => expiryFee([{ amount: 100, expiry: 200 }], -.1));
});
