use crate::circuit::*;
use crate::{hash, limb, Id, F};
use ff::{Field, PrimeField};

#[derive(Clone)]
struct Tree {
    table: usize,
    levels: Vec<Vec<F>>,
}

impl Tree {
    fn new(table: usize) -> Self {
        let mut levels = vec![vec![empty_leaf(table); 1 << DEPTH]];
        for height in 0..DEPTH {
            let below = &levels[height];
            let parent = hash(&[F::from(node_tag(table, height)), below[0], below[0]]);
            levels.push(vec![parent; below.len() / 2]);
        }
        Self { table, levels }
    }

    fn slot(id: Id) -> usize {
        (id[1] as usize) & ((1 << DEPTH) - 1)
    }

    fn root(&self) -> F {
        self.levels[DEPTH][0]
    }

    fn path(&self, id: Id, expected: F) -> Result<[F; DEPTH], &'static str> {
        let slot = Self::slot(id);
        if self.levels[0][slot] != expected {
            return Err("membership or vacancy check failed");
        }
        Ok(std::array::from_fn(|height| {
            self.levels[height][(slot >> height) ^ 1]
        }))
    }

    fn replace(&mut self, id: Id, old: F, new: F) -> Result<[F; DEPTH], &'static str> {
        let path = self.path(id, old)?;
        let mut slot = Self::slot(id);
        self.levels[0][slot] = new;
        for height in 0..DEPTH {
            let left = slot & !1;
            let parent = hash(&[
                F::from(node_tag(self.table, height)),
                self.levels[height][left],
                self.levels[height][left + 1],
            ]);
            slot >>= 1;
            self.levels[height + 1][slot] = parent;
        }
        Ok(path)
    }
}

#[derive(Clone)]
pub struct Ledger {
    tables: [Tree; 4],
    public: State,
}

impl Ledger {
    pub fn empty(context: F) -> Self {
        let tables = std::array::from_fn(Tree::new);
        let mut public = [F::ZERO; ARITY];
        for (table, tree) in tables.iter().enumerate() {
            public[table] = tree.root();
        }
        public[CONTEXT] = context;
        Self { tables, public }
    }

    pub fn state(&self) -> State {
        self.public
    }

    pub fn apply(&mut self, mut step: CashuStep) -> Result<CashuStep, &'static str> {
        let mut next = self.clone();
        next.transition(&mut step)?;
        *self = next;
        Ok(step)
    }

    fn transition(&mut self, step: &mut CashuStep) -> Result<(), &'static str> {
        let [reserve, intent, live, spent] = &mut self.tables;
        let binding = reserve_ref(step.reserve);
        let amount = step.amount;
        if !(1..=MAX_SATS).contains(&amount) {
            return Err("invalid amount");
        }
        let mut output_amounts = [0, 0];
        let empty_reserve = empty_leaf(RESERVE);
        let empty_intent = empty_leaf(INTENT);
        let empty_live = empty_leaf(LIVE);
        let empty_spent = empty_leaf(SPENT);
        let [assets, pending, liabilities] = [ASSETS, PENDING, LIABILITIES].map(|index| {
            let repr = self.public[index].to_repr();
            u64::from_le_bytes(repr.as_ref()[..8].try_into().unwrap())
        });
        let (assets, pending, liabilities) = match step.operation {
            Operation::Register => {
                step.paths[0] = reserve.replace(
                    step.reserve,
                    empty_reserve,
                    entry(RESERVE, step.reserve, F::ZERO, amount),
                )?;
                step.paths[1] = intent.replace(
                    step.intent,
                    empty_intent,
                    entry(INTENT, step.intent, binding, amount),
                )?;
                (assets + amount, pending + amount, liabilities)
            }
            Operation::Issue => {
                step.paths[1] = intent.replace(
                    step.intent,
                    entry(INTENT, step.intent, binding, amount),
                    entry(INTENT, step.intent, binding, 0),
                )?;
                output_amounts[0] = amount;
                (
                    assets,
                    pending
                        .checked_sub(amount)
                        .ok_or("insufficient pending balance")?,
                    liabilities + amount,
                )
            }
            Operation::Split => {
                output_amounts = [
                    step.split_first,
                    amount
                        .checked_sub(step.split_first)
                        .ok_or("split underflow")?,
                ];
                if output_amounts.contains(&0) {
                    return Err("zero split output");
                }
                (assets, pending, liabilities)
            }
            Operation::Swap => {
                output_amounts[0] = amount;
                (assets, pending, liabilities)
            }
            Operation::Redeem => {
                let before = step.reserve_before;
                let after = before.checked_sub(amount).ok_or("insufficient reserve")?;
                step.paths[0] = reserve.replace(
                    step.reserve,
                    entry(RESERVE, step.reserve, F::ZERO, before),
                    entry(RESERVE, step.reserve, F::ZERO, after),
                )?;
                (
                    assets.checked_sub(amount).ok_or("insufficient assets")?,
                    pending,
                    liabilities
                        .checked_sub(amount)
                        .ok_or("insufficient liabilities")?,
                )
            }
        };
        if assets > MAX_SATS || pending + liabilities > assets {
            return Err("insolvent accounting state");
        }

        if matches!(
            step.operation,
            Operation::Split | Operation::Swap | Operation::Redeem
        ) {
            step.paths[2] = live.replace(
                step.input,
                entry(LIVE, step.input, binding, amount),
                empty_live,
            )?;
            step.paths[3] = spent.replace(
                step.input,
                empty_spent,
                entry(SPENT, step.input, binding, amount),
            )?;
        }
        for (index, sats) in output_amounts
            .into_iter()
            .enumerate()
            .filter(|(_, sats)| *sats != 0)
        {
            let id = step.outputs[index];
            step.paths[4 + 2 * index] = spent.path(id, empty_spent)?;
            step.paths[5 + 2 * index] =
                live.replace(id, empty_live, entry(LIVE, id, binding, sats))?;
        }
        for (table, tree) in self.tables.iter().enumerate() {
            self.public[table] = tree.root();
        }
        self.public[ASSETS] = F::from(assets);
        self.public[PENDING] = F::from(pending);
        self.public[LIABILITIES] = F::from(liabilities);
        self.public[SEQUENCE] += F::ONE;
        let [reserve_hi, reserve_lo] = step.reserve.map(limb);
        let [intent_hi, intent_lo] = step.intent.map(limb);
        let [input_hi, input_lo] = step.input.map(limb);
        let [[first_hi, first_lo], [second_hi, second_lo]] = step.outputs.map(|id| id.map(limb));
        let [evidence_hi, evidence_lo] = step.evidence.map(limb);
        self.public[JOURNAL] = hash(&[
            F::from(EVENT_TAG),
            self.public[CONTEXT],
            self.public[JOURNAL],
            self.public[SEQUENCE],
            F::from(step.operation as u64 + 1),
            reserve_hi,
            reserve_lo,
            intent_hi,
            intent_lo,
            input_hi,
            input_lo,
            first_hi,
            first_lo,
            second_hi,
            second_lo,
            F::from(amount),
            F::from(step.split_first),
            evidence_hi,
            evidence_lo,
        ]);
        Ok(())
    }
}
