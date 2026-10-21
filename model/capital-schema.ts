// JSON Schema and runtime validation share the same structural definitions.
// Accounting and causal predicates remain in CapitalAccountingMachine.
type Schema = { type?: string | string[]; const?: unknown; enum?: unknown[]; minimum?: number; maximum?: number;
  minLength?: number; items?: Schema; uniqueItems?: boolean; properties?: Record<string, Schema>;
  required?: string[]; additionalProperties?: boolean | Schema; anyOf?: Schema[]; oneOf?: Schema[] };
const id: Schema = { type: "string", minLength: 1 };
const integer: Schema = { type: "integer", minimum: 0, maximum: Number.MAX_SAFE_INTEGER };
const ids: Schema = { type: "array", items: id, uniqueItems: true };
const nullable = (s: Schema): Schema => ({ anyOf: [s, { type: "null" }] });
const object = (properties: Record<string, Schema>, optional: string[] = []): Schema => ({ type: "object", properties,
  required: Object.keys(properties).filter(k => !optional.includes(k)), additionalProperties: false });
const claim = object({ claim_id: id, claimant: id, allocations: { type: "object", additionalProperties: integer }, expiry_height: integer, parent_claim_id: id }, ["parent_claim_id"]);
const request = object({ operation_id: id, holder: id, input_claim_ids: ids, reserve_ids: ids, channel_id: id, delivered: integer, max_fee: integer, timeout_height: integer,
  change_backing: { const: "retained" }, max_holder_fee: integer }, ["change_backing", "max_holder_fee"]);
const operation = object({ operation_id: id });
const blocks: Schema = { type: "array", items: object({ height: integer, hash: id, parent_hash: id }) };
const roundRefresh = object({ operation_id: id, input_claim_ids: ids, backing_ids: ids, service_fee: integer, replacement: claim });
const onchainTransaction = object({ input_ids: ids, outputs: { type: "array", items: object({ asset_id: id, amount: integer, output_index: integer, release_height: integer }, ["release_height"]) },
  fee: integer, inclusion_height: integer, inclusion_hash: id, refresh: roundRefresh,
  reuse: object({ sweep_id: id, recovery_allocations: { type: "object", additionalProperties: integer } }) }, ["refresh", "reuse"]);
export const payloadSchemas: Record<string, Schema> = {
  FUND: object({ asset_id: id, owner: id, location: { const: "onchain" }, backing_ref: id, maturity_height: integer, pool: { type: "boolean" } }),
  OPEN_CHANNEL: object({ channel_id: id, asset_id: id, funding_ref: id, remote: integer, spendable: integer, receivable: integer }),
  CHANNEL_CAPACITY: object({ channel_id: id, local: integer, remote: integer, spendable: integer, receivable: integer }),
  ISSUE_VTXO: object({ claim, service_fee: integer }, ["service_fee"]), RECEIVE_LIGHTNING: object({ channel_id: id, asset_id: id, fee: integer, claim,
    backing_mode: { const: "inventory" }, service_fee: integer, pool: { type: "boolean" }, settlement_evidence_ref: id },
    ["backing_mode", "service_fee", "pool", "settlement_evidence_ref"]),
  PAYMENT_OFFERED: object({ operation_id: id, holder: id }),
  REQUEST_OUTGOING: request, CANCEL_REQUEST: operation,
  HTLC_ACCEPTED: object({ operation_id: id, in_flight_amount: integer, observed_spendable: integer }, ["in_flight_amount", "observed_spendable"]),
  HTLC_SETTLED: object({ operation_id: id, fee: integer, service_fee: integer, preimage_evidence_ref: id, change: claim }, ["change", "service_fee"]),
  HTLC_FAILED: operation,
  RESOLVE_FAILED: object({ operation_id: id, path: { enum: ["revocation", "timeout"] }, resolution_height: integer, resolution_hash: id,
    replacements: { type: "array", items: claim } }, ["resolution_height", "resolution_hash", "replacements"]),
  REFRESH: object({ operation_id: id, input_claim_ids: ids, reserve_ids: ids, fee: integer, replacement: claim }),
  EXPIRY_REACHED: operation,
  SWEEP_BROADCAST: object({ sweep_id: id, operation_id: id, output_id: id, destination: id, fee: integer, input_outpoints: ids }),
  SWEEP_CONFIRMED: object({ sweep_id: id, inclusion_height: integer, inclusion_hash: id }),
  CAPITAL_REUSABLE: object({ sweep_id: id, reuse: request, channel_funding_ref: id, funding_height: integer, funding_hash: id, spendable: integer }),
  MOVE_TO_CHANNEL: object({ asset_id: id, channel_id: id, funding_ref: id, remote: integer, spendable: integer, receivable: integer }),
  SPLIT_MERGE: object({ input_ids: ids, outputs: { type: "array", items: object({ asset_id: id, amount: integer }) } }),
  ONCHAIN_TRANSACTION: onchainTransaction,
  BACKING_EXPIRED: object({ input_ids: ids }),
  RECOVERY_SWEEP: object({ sweep_id: id, operation_ids: ids, input_ids: ids, output_id: id, destination: id, fee: integer, input_outpoints: ids }),
  EXIT: object({ claim_id: id, fee: integer, output_id: id, destination: id, mode: { enum: ["cooperative", "unilateral"] }, inclusion_height: integer, inclusion_hash: id,
    funding: object({ operation_id: id, transaction: onchainTransaction, connector_ids: ids, recovery_claim: claim }) }, ["funding"]),
  CHAIN: object({ blocks }), TICK: object({}), REORG: object({ blocks }),
};
const envelope = object({ event_id: id, trace_id: id, event_type: { enum: Object.keys(payloadSchemas) }, amount: integer, unit: { const: "msat" },
  asset_ids: ids, claim_ids: ids, causal_parent_ids: ids, block_height: integer, block_hash: nullable(id), monotonic_timestamp: nullable(integer), txid: nullable(id), evidence_refs: ids, data: { type: "object" } });
export const capitalEventSchema = { $schema: "https://json-schema.org/draft/2020-12/schema", title: "Spiral capital event v1",
  ...envelope, oneOf: Object.entries(payloadSchemas).map(([type, data]) => ({ properties: { event_type: { const: type }, data } })) };

/** Evaluates only the JSON Schema vocabulary used above, with no coercion. */
function matches(s: Schema, value: unknown): boolean {
  if (s.const !== undefined && value !== s.const) return false;
  if (s.enum && !s.enum.includes(value)) return false;
  if (s.anyOf && !s.anyOf.some(x => matches(x, value))) return false;
  if (s.oneOf && s.oneOf.filter(x => matches(x, value)).length !== 1) return false;
  if (s.type) {
    const actual = value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
    if (s.type === "integer" ? !Number.isSafeInteger(value) : s.type !== actual) return false;
  }
  if (typeof value === "number" && (!Number.isFinite(value) || (s.minimum !== undefined && value < s.minimum) || (s.maximum !== undefined && value > s.maximum))) return false;
  if (typeof value === "string" && s.minLength !== undefined && value.length < s.minLength) return false;
  if (Array.isArray(value)) {
    if (s.items && !value.every(v => matches(s.items!, v))) return false;
    if (s.uniqueItems && new Set(value.map(v => JSON.stringify(v))).size !== value.length) return false;
  } else if (value !== null && typeof value === "object") {
    const v = value as Record<string, unknown>;
    if (s.required?.some(k => !Object.hasOwn(v, k))) return false;
    for (const [key, x] of Object.entries(v)) {
      if (s.properties && Object.hasOwn(s.properties, key)) { if (!matches(s.properties[key], x)) return false; }
      else if (s.additionalProperties === false) return false;
      else if (typeof s.additionalProperties === "object" && !matches(s.additionalProperties, x)) return false;
    }
  }
  return true;
}
export function validateEventShape(value: unknown): void {
  if (!matches(capitalEventSchema, value)) throw new Error("event does not match capital-event.schema.json");
}
