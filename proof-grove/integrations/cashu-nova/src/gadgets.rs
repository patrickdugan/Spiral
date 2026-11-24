//! R1CS helpers adapted from zk-rusto-no-bitcoino's Ark transition integration.

use crate::{constants, F};
use ff::{Field, PrimeFieldBits};
use nova_snark::frontend::gadgets::poseidon::{
    Elt, IOPattern, Simplex, SpongeAPI, SpongeCircuit, SpongeOp, SpongeTrait,
};
use nova_snark::frontend::num::AllocatedNum;
use nova_snark::frontend::{ConstraintSystem, Index, LinearCombination, Variable};

fn one() -> Variable {
    Variable::new_unchecked(Index::Input(0))
}

/// A linear combination with its value (zero when synthesizing the shape).
#[derive(Clone)]
pub(crate) struct V {
    lc: LinearCombination<F>,
    val: F,
}

impl V {
    pub(crate) fn c(x: F) -> V {
        V {
            lc: LinearCombination::zero() + (x, one()),
            val: x,
        }
    }
    pub(crate) fn cu(x: u64) -> V {
        V::c(F::from(x))
    }
    pub(crate) fn zero() -> V {
        V {
            lc: LinearCombination::zero(),
            val: F::ZERO,
        }
    }
    pub(crate) fn var(n: &AllocatedNum<F>) -> V {
        V {
            lc: LinearCombination::zero() + n.get_variable(),
            val: n.get_value().unwrap_or(F::ZERO),
        }
    }
    pub(crate) fn add(&self, o: &V) -> V {
        V {
            lc: self.lc.clone() + &o.lc,
            val: self.val + o.val,
        }
    }
    pub(crate) fn sub(&self, o: &V) -> V {
        V {
            lc: self.lc.clone() - &o.lc,
            val: self.val - o.val,
        }
    }
    pub(crate) fn scale(&self, k: F) -> V {
        let mut lc = LinearCombination::zero();
        for (v, c) in self.lc.iter() {
            lc = lc + (*c * k, v);
        }
        V {
            lc,
            val: self.val * k,
        }
    }
}

fn bits_of(x: &F, n: usize) -> Vec<bool> {
    x.to_le_bits().iter().take(n).map(|b| *b).collect()
}

pub(crate) struct Cx<'a, CS: ConstraintSystem<F>> {
    pub(crate) cs: &'a mut CS,
    pub(crate) n: usize,
}

impl<'a, CS: ConstraintSystem<F>> Cx<'a, CS> {
    fn name(&mut self) -> String {
        self.n += 1;
        format!("g{}", self.n)
    }
    pub(crate) fn alloc(&mut self, val: F) -> V {
        let nm = self.name();
        let a = AllocatedNum::alloc_infallible(self.cs.namespace(|| nm), || val);
        V {
            lc: LinearCombination::zero() + a.get_variable(),
            val,
        }
    }
    fn alloc_num(&mut self, val: F) -> AllocatedNum<F> {
        let nm = self.name();
        AllocatedNum::alloc_infallible(self.cs.namespace(|| nm), || val)
    }
    fn enforce(&mut self, a: &V, b: &V, c: &V) {
        let nm = self.name();
        self.cs
            .enforce(|| nm, |l| l + &a.lc, |l| l + &b.lc, |l| l + &c.lc);
    }
    pub(crate) fn eq(&mut self, a: &V, b: &V) {
        self.enforce(&a.sub(b), &V::cu(1), &V::zero());
    }
    pub(crate) fn mul(&mut self, a: &V, b: &V) -> V {
        let c = self.alloc(a.val * b.val);
        self.enforce(a, b, &c);
        c
    }
    pub(crate) fn prod_zero(&mut self, a: &V, b: &V) {
        self.enforce(a, b, &V::zero());
    }
    pub(crate) fn bit(&mut self, b: bool) -> V {
        let v = self.alloc(if b { F::ONE } else { F::ZERO });
        self.prod_zero(&v, &V::cu(1).sub(&v));
        v
    }
    /// x as an integer below 2^n: n boolean bits that recompose to x.
    pub(crate) fn range(&mut self, x: &V, n: usize) -> Vec<V> {
        let bs = bits_of(&x.val, n);
        let mut acc = V::zero();
        let mut result = Vec::with_capacity(n);
        for (i, &b) in bs.iter().enumerate() {
            let v = self.bit(b);
            acc = acc.add(&v.scale(F::from(2).pow_vartime([i as u64])));
            result.push(v);
        }
        self.eq(&acc, x);
        result
    }
    pub(crate) fn output(&mut self, v: &V) -> AllocatedNum<F> {
        let out = self.alloc_num(v.val);
        self.eq(&V::var(&out), v);
        out
    }
    pub(crate) fn hash(&mut self, xs: &[V]) -> V {
        let nums: Vec<AllocatedNum<F>> = xs
            .iter()
            .map(|x| {
                let a = self.alloc_num(x.val);
                let v = V::var(&a);
                self.eq(&v, x);
                a
            })
            .collect();
        let nm = self.name();
        let mut ns = self.cs.namespace(|| nm);
        let mut sponge = SpongeCircuit::new_with_constants(constants(), Simplex);
        sponge.start(
            IOPattern(vec![
                SpongeOp::Absorb(nums.len() as u32),
                SpongeOp::Squeeze(1),
            ]),
            None,
            &mut ns,
        );
        let elts: Vec<Elt<F>> = nums.into_iter().map(Elt::Allocated).collect();
        SpongeAPI::absorb(&mut sponge, elts.len() as u32, &elts, &mut ns);
        let out = SpongeAPI::squeeze(&mut sponge, 1, &mut ns);
        sponge.finish(&mut ns).unwrap();
        let a = Elt::ensure_allocated(&out[0], &mut ns.namespace(|| "out")).unwrap();
        V::var(&a)
    }
    /// a when c = 0, b when c = 1.
    pub(crate) fn sel(&mut self, c: &V, a: &V, b: &V) -> V {
        let d = self.mul(c, &b.sub(a));
        a.add(&d)
    }
}
