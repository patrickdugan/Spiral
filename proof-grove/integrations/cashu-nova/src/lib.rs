//! Recursive accounting for the Proof Grove protected Cashu profile.
//! Bitcoin, Cashu signatures and holder authorization are checked at admission.

mod check;
mod circuit;
mod gadgets;
mod witness;
pub use check::check_step;
pub use circuit::{CashuStep, Operation, State, ARITY, DEPTH};
pub use witness::Ledger;

use ff::{Field, PrimeField};
use generic_array::typenum::U5;
use nova_snark::frontend::gadgets::poseidon::{
    IOPattern, PoseidonConstants, Simplex, Sponge, SpongeAPI, SpongeOp, SpongeTrait, Strength,
};
use nova_snark::provider::PallasEngine;
use nova_snark::traits::Engine;
use sha2::{Digest, Sha256};
use std::sync::OnceLock;

pub type F = <PallasEngine as Engine>::Scalar;
pub type Id = [u128; 2];

pub(crate) fn constants() -> &'static PoseidonConstants<F, U5> {
    static CONSTANTS: OnceLock<PoseidonConstants<F, U5>> = OnceLock::new();
    CONSTANTS.get_or_init(|| Sponge::<F, U5>::api_constants(Strength::Standard))
}

pub fn commitment(domain: &str, payload: &[u8]) -> Id {
    let domain = domain.as_bytes();
    let mut hash = Sha256::new();
    hash.update(b"proof-grove/cashu-nova/v1\0");
    hash.update((domain.len() as u64).to_be_bytes());
    hash.update(domain);
    hash.update(payload);
    let digest = hash.finalize();
    [
        u128::from_be_bytes(digest[..16].try_into().unwrap()),
        u128::from_be_bytes(digest[16..].try_into().unwrap()),
    ]
}

pub fn field_hex(value: F) -> String {
    let bytes = value.to_repr();
    hex::encode(bytes.as_ref().iter().copied().rev().collect::<Vec<_>>())
}

pub fn field_from_hex(encoded: &str) -> Option<F> {
    if encoded.len() != 64 {
        return None;
    }
    let mut bytes = <F as PrimeField>::Repr::default();
    hex::decode_to_slice(encoded, bytes.as_mut()).ok()?;
    bytes.as_mut().reverse();
    F::from_repr_vartime(bytes)
}

pub(crate) fn limb(value: u128) -> F {
    F::from(value as u64) + F::from((value >> 64) as u64) * F::from(2).pow_vartime([64])
}

pub(crate) fn hash(items: &[F]) -> F {
    let mut sponge = Sponge::new_with_constants(constants(), Simplex);
    let count = items.len() as u32;
    sponge.start(
        IOPattern(vec![SpongeOp::Absorb(count), SpongeOp::Squeeze(1)]),
        None,
        &mut (),
    );
    SpongeAPI::absorb(&mut sponge, count, items, &mut ());
    let result = SpongeAPI::squeeze(&mut sponge, 1, &mut ());
    sponge.finish(&mut ()).unwrap();
    result[0]
}

pub fn context(id: Id) -> F {
    hash(&[F::from(circuit::CONTEXT_TAG), limb(id[0]), limb(id[1])])
}
