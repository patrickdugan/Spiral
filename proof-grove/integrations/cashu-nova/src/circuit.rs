use crate::gadgets::{Cx, V};
use crate::{hash, limb, Id, F};
use nova_snark::frontend::num::AllocatedNum;
use nova_snark::frontend::{ConstraintSystem, SynthesisError};
use nova_snark::traits::circuit::StepCircuit;

pub const DEPTH: usize = 8;
pub const ARITY: usize = 10;
pub type State = [F; ARITY];
pub(crate) const MAX_SATS: u64 = 2_100_000_000_000_000;
pub(crate) const CONTEXT_TAG: u64 = 0x50474331;
pub(crate) const RESERVE_TAG: u64 = 0x50475231;
pub(crate) const EVENT_TAG: u64 = 0x50474531;
const AMOUNT_BITS: usize = 51;

pub(crate) const RESERVE: usize = 0;
pub(crate) const INTENT: usize = 1;
pub(crate) const LIVE: usize = 2;
pub(crate) const SPENT: usize = 3;
pub(crate) const ASSETS: usize = 4;
pub(crate) const PENDING: usize = 5;
pub(crate) const LIABILITIES: usize = 6;
pub(crate) const SEQUENCE: usize = 7;
pub(crate) const JOURNAL: usize = 8;
pub(crate) const CONTEXT: usize = 9;

#[derive(Clone, Copy, Default)]
pub enum Operation {
    #[default]
    Register,
    Issue,
    Split,
    Swap,
    Redeem,
}

#[derive(Clone, Default)]
pub struct CashuStep {
    pub operation: Operation,
    pub reserve: Id,
    pub intent: Id,
    pub input: Id,
    pub outputs: [Id; 2],
    pub evidence: Id,
    pub amount: u64,
    pub split_first: u64,
    pub reserve_before: u64,
    pub(crate) paths: [[F; DEPTH]; 8],
}

pub(crate) fn leaf_tag(table: usize) -> u64 {
    0x50474c10 + table as u64
}

pub(crate) fn node_tag(table: usize, height: usize) -> u64 {
    0x50474e00 + 16 * table as u64 + height as u64
}

pub(crate) fn empty_leaf(table: usize) -> F {
    hash(&[F::from(0x50474d10 + table as u64)])
}

pub(crate) fn reserve_ref(id: Id) -> F {
    hash(&[F::from(RESERVE_TAG), limb(id[0]), limb(id[1])])
}

pub(crate) fn entry(table: usize, id: Id, binding: F, sats: u64) -> F {
    hash(&[
        F::from(leaf_tag(table)),
        limb(id[0]),
        limb(id[1]),
        binding,
        F::from(sats),
    ])
}

struct Key {
    hi: V,
    lo: V,
    route: Vec<V>,
}

impl Key {
    fn alloc<CS: ConstraintSystem<F>>(cx: &mut Cx<CS>, id: Id) -> Self {
        let hi = cx.alloc(limb(id[0]));
        let lo = cx.alloc(limb(id[1]));
        cx.range(&hi, 128);
        let route = cx.range(&lo, 128);
        Self { hi, lo, route }
    }

    fn entry<CS: ConstraintSystem<F>>(
        &self,
        cx: &mut Cx<CS>,
        table: usize,
        binding: &V,
        sats: &V,
    ) -> V {
        cx.hash(&[
            V::cu(leaf_tag(table)),
            self.hi.clone(),
            self.lo.clone(),
            binding.clone(),
            sats.clone(),
        ])
    }
}

fn root<CS: ConstraintSystem<F>>(
    cx: &mut Cx<CS>,
    table: usize,
    key: &Key,
    mut leaf: V,
    siblings: &[V; DEPTH],
) -> V {
    for (height, (side, sibling)) in key.route.iter().zip(siblings).enumerate() {
        let left = cx.sel(side, &leaf, sibling);
        let right = cx.sel(side, sibling, &leaf);
        leaf = cx.hash(&[V::cu(node_tag(table, height)), left, right]);
    }
    leaf
}

struct Path<'a> {
    table: usize,
    key: &'a Key,
    siblings: &'a [F; DEPTH],
}

impl Path<'_> {
    fn open<CS: ConstraintSystem<F>>(
        &self,
        cx: &mut Cx<CS>,
        tree: &V,
        active: &V,
        old: V,
    ) -> [V; DEPTH] {
        let siblings = self.siblings.map(|sibling| cx.alloc(sibling));
        let calculated = root(cx, self.table, self.key, old, &siblings);
        cx.prod_zero(active, &calculated.sub(tree));
        siblings
    }

    fn replace<CS: ConstraintSystem<F>>(
        &self,
        cx: &mut Cx<CS>,
        tree: &V,
        active: &V,
        old: V,
        new: V,
    ) -> V {
        let siblings = self.open(cx, tree, active, old);
        let updated = root(cx, self.table, self.key, new, &siblings);
        cx.sel(active, tree, &updated)
    }
}

impl StepCircuit<F> for CashuStep {
    fn arity(&self) -> usize {
        ARITY
    }

    fn synthesize<CS: ConstraintSystem<F>>(
        &self,
        cs: &mut CS,
        input: &[AllocatedNum<F>],
    ) -> Result<Vec<AllocatedNum<F>>, SynthesisError> {
        let mut cx = Cx { cs, n: 0 };
        let mut z: Vec<V> = input.iter().map(V::var).collect();
        let one = V::cu(1);
        let zero = V::zero();
        let flags: [V; 5] = std::array::from_fn(|index| cx.bit(self.operation as usize == index));
        let [register, issue, split, swap, redeem] = &flags;
        cx.eq(&flags.iter().fold(V::zero(), |sum, bit| sum.add(bit)), &one);
        let retire = split.add(swap).add(redeem);
        let create = split.add(swap).add(issue);
        let amounts = [self.amount, self.split_first, self.reserve_before];
        let [amount, first, before] = amounts.map(|sats| cx.alloc(F::from(sats)));
        let second = amount.sub(&first);
        let remainder = before.sub(&amount);
        cx.range(&amount.sub(&one), AMOUNT_BITS);
        cx.range(&V::cu(MAX_SATS).sub(&amount), AMOUNT_BITS);
        for value in [&first.sub(&one), &second.sub(&one)] {
            let positive_split = cx.mul(split, value);
            cx.range(&positive_split, AMOUNT_BITS);
        }
        let reserve_after = cx.mul(redeem, &remainder);
        cx.range(&reserve_after, AMOUNT_BITS);
        let reserved_before = cx.mul(redeem, &before);
        cx.range(&reserved_before, AMOUNT_BITS);

        let reserve = Key::alloc(&mut cx, self.reserve);
        let intent = Key::alloc(&mut cx, self.intent);
        let source = Key::alloc(&mut cx, self.input);
        let outputs = self.outputs.map(|id| Key::alloc(&mut cx, id));
        let binding = cx.hash(&[V::cu(RESERVE_TAG), reserve.hi.clone(), reserve.lo.clone()]);

        let existing = reserve.entry(&mut cx, RESERVE, &zero, &before);
        let vacant = V::c(empty_leaf(RESERVE));
        let old = cx.sel(redeem, &vacant, &existing);
        let value = cx.sel(redeem, &amount, &remainder);
        let new = reserve.entry(&mut cx, RESERVE, &zero, &value);
        z[RESERVE] = Path {
            table: RESERVE,
            key: &reserve,
            siblings: &self.paths[0],
        }
        .replace(&mut cx, &z[RESERVE], &register.add(redeem), old, new);

        let pending = intent.entry(&mut cx, INTENT, &binding, &amount);
        let used = intent.entry(&mut cx, INTENT, &binding, &zero);
        let old = cx.sel(issue, &V::c(empty_leaf(INTENT)), &pending);
        let new = cx.sel(issue, &pending, &used);
        z[INTENT] = Path {
            table: INTENT,
            key: &intent,
            siblings: &self.paths[1],
        }
        .replace(&mut cx, &z[INTENT], &register.add(issue), old, new);

        let live = source.entry(&mut cx, LIVE, &binding, &amount);
        let empty_live = V::c(empty_leaf(LIVE));
        z[LIVE] = Path {
            table: LIVE,
            key: &source,
            siblings: &self.paths[2],
        }
        .replace(&mut cx, &z[LIVE], &retire, live, empty_live.clone());

        let spent = source.entry(&mut cx, SPENT, &binding, &amount);
        let empty_spent = V::c(empty_leaf(SPENT));
        z[SPENT] = Path {
            table: SPENT,
            key: &source,
            siblings: &self.paths[3],
        }
        .replace(&mut cx, &z[SPENT], &retire, empty_spent.clone(), spent);

        let output_amounts = [cx.sel(split, &amount, &first), second];
        for (index, ((key, value), active)) in outputs
            .iter()
            .zip(output_amounts)
            .zip([&create, split])
            .enumerate()
        {
            Path {
                table: SPENT,
                key,
                siblings: &self.paths[4 + 2 * index],
            }
            .open(&mut cx, &z[SPENT], active, empty_spent.clone());
            let output = key.entry(&mut cx, LIVE, &binding, &value);
            z[LIVE] = Path {
                table: LIVE,
                key,
                siblings: &self.paths[5 + 2 * index],
            }
            .replace(&mut cx, &z[LIVE], active, empty_live.clone(), output);
        }

        let funded = cx.mul(register, &amount);
        let minted = cx.mul(issue, &amount);
        let redeemed = cx.mul(redeem, &amount);
        z[ASSETS] = z[ASSETS].add(&funded).sub(&redeemed);
        z[PENDING] = z[PENDING].add(&funded).sub(&minted);
        z[LIABILITIES] = z[LIABILITIES].add(&minted).sub(&redeemed);
        for total in &z[ASSETS..=LIABILITIES] {
            cx.range(total, AMOUNT_BITS);
            cx.range(&V::cu(MAX_SATS).sub(total), AMOUNT_BITS);
        }
        cx.range(
            &z[ASSETS].sub(&z[PENDING]).sub(&z[LIABILITIES]),
            AMOUNT_BITS,
        );
        z[SEQUENCE] = z[SEQUENCE].add(&one);
        cx.range(&z[SEQUENCE], 32);

        let kind = flags
            .iter()
            .enumerate()
            .fold(V::zero(), |sum, (index, bit)| {
                sum.add(&bit.scale(F::from(index as u64 + 1)))
            });
        let evidence = Key::alloc(&mut cx, self.evidence);
        z[JOURNAL] = cx.hash(&[
            V::cu(EVENT_TAG),
            z[CONTEXT].clone(),
            z[JOURNAL].clone(),
            z[SEQUENCE].clone(),
            kind,
            reserve.hi,
            reserve.lo,
            intent.hi,
            intent.lo,
            source.hi,
            source.lo,
            outputs[0].hi.clone(),
            outputs[0].lo.clone(),
            outputs[1].hi.clone(),
            outputs[1].lo.clone(),
            amount,
            first,
            evidence.hi,
            evidence.lo,
        ]);
        Ok(z.iter().map(|value| cx.output(value)).collect())
    }
}
