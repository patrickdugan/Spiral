//! Fast R1CS constraint evaluation adapted from the Ark Nova integration.
use crate::{CashuStep, State, F};
use ff::Field;
use nova_snark::frontend::num::AllocatedNum;
use nova_snark::frontend::{ConstraintSystem, Index, LinearCombination, SynthesisError, Variable};
use nova_snark::traits::circuit::StepCircuit;

/// A constraint system that evaluates each constraint as it is enforced: the fast satisfiability test.
pub struct CheckCS {
    inputs: Vec<F>,
    aux: Vec<F>,
    pub n: usize,
    pub first_failure: Option<usize>,
}

impl ConstraintSystem<F> for CheckCS {
    type Root = Self;
    fn new() -> Self {
        CheckCS {
            inputs: vec![F::ONE],
            aux: vec![],
            n: 0,
            first_failure: None,
        }
    }
    fn alloc<Fn_, A, AR>(&mut self, _a: A, f: Fn_) -> Result<Variable, SynthesisError>
    where
        Fn_: FnOnce() -> Result<F, SynthesisError>,
        A: FnOnce() -> AR,
        AR: Into<String>,
    {
        self.aux.push(f()?);
        Ok(Variable::new_unchecked(Index::Aux(self.aux.len() - 1)))
    }
    fn alloc_input<Fn_, A, AR>(&mut self, _a: A, f: Fn_) -> Result<Variable, SynthesisError>
    where
        Fn_: FnOnce() -> Result<F, SynthesisError>,
        A: FnOnce() -> AR,
        AR: Into<String>,
    {
        self.inputs.push(f()?);
        Ok(Variable::new_unchecked(Index::Input(self.inputs.len() - 1)))
    }
    fn enforce<A, AR, LA, LB, LC>(&mut self, _a: A, a: LA, b: LB, c: LC)
    where
        A: FnOnce() -> AR,
        AR: Into<String>,
        LA: FnOnce(LinearCombination<F>) -> LinearCombination<F>,
        LB: FnOnce(LinearCombination<F>) -> LinearCombination<F>,
        LC: FnOnce(LinearCombination<F>) -> LinearCombination<F>,
    {
        let ev = |l: LinearCombination<F>| l.eval(&self.inputs, &self.aux);
        let (x, y, zc) = (
            ev(a(LinearCombination::zero())),
            ev(b(LinearCombination::zero())),
            ev(c(LinearCombination::zero())),
        );
        if x * y != zc && self.first_failure.is_none() {
            self.first_failure = Some(self.n);
        }
        self.n += 1;
    }
    fn push_namespace<NR, N>(&mut self, _n: N)
    where
        NR: Into<String>,
        N: FnOnce() -> NR,
    {
    }
    fn pop_namespace(&mut self) {}
    fn get_root(&mut self) -> &mut Self {
        self
    }
}

pub fn check_step(previous: &State, step: &CashuStep) -> Result<(State, usize), usize> {
    let mut cs = CheckCS::new();
    let input: Vec<_> = previous
        .iter()
        .enumerate()
        .map(|(i, value)| {
            AllocatedNum::alloc_infallible(cs.namespace(|| format!("z{i}")), || *value)
        })
        .collect();
    let output = step
        .synthesize(&mut cs, &input)
        .expect("fixed circuit shape");
    if let Some(index) = cs.first_failure {
        return Err(index);
    }
    Ok((
        std::array::from_fn(|i| output[i].get_value().unwrap()),
        cs.n,
    ))
}
