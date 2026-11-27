"""Restricted payout graph: delivery, the cut condition, and min-cost-flow dual prices.

Network: source -> vault v (capacity C_v) -> creditor j (capacity u_vj) -> sink (demand d_j).
Full delivery holds iff for every creditor subset J,
    sum_{j in J} d_j <= sum_v min(C_v, sum_{j in J} u_vj)            (cut condition)
which is max-flow/min-cut for this three-layer network.
"""
from __future__ import annotations

import itertools

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix


def bipartite_maxflow(C, U, d):
    """Max delivery per creditor. C: (V,), U: (V,J) edge capacities, d: (J,). Returns (J,)."""
    C, U, d = np.asarray(C, float), np.asarray(U, float), np.asarray(d, float)
    V, J = U.shape
    edges = [(v, j) for v in range(V) for j in range(J) if U[v, j] > 0]
    if not edges or C.sum() <= 0:
        return np.zeros(J)
    n = len(edges)
    A = lil_matrix((V + J, n))
    for e, (v, j) in enumerate(edges):
        A[v, e] = 1.0
        A[V + j, e] = 1.0
    b = np.concatenate([C, d])
    res = linprog(-np.ones(n), A_ub=A.tocsr(), b_ub=b, bounds=[(0, U[v, j]) for v, j in edges], method="highs")
    if res.status != 0:
        raise RuntimeError(res.message)
    out = np.zeros(J)
    for e, (v, j) in enumerate(edges):
        out[j] += res.x[e]
    return np.minimum(out, d)


def cut_condition(C, U, d):
    """Brute-force check of the cut condition over all creditor subsets (small J only).
    Returns (holds, worst_deficit, worst_subset)."""
    C, U, d = np.asarray(C, float), np.asarray(U, float), np.asarray(d, float)
    J = len(d)
    worst = (0.0, ())
    for r in range(1, J + 1):
        for S in itertools.combinations(range(J), r):
            S = list(S)
            rhs = np.minimum(C, U[:, S].sum(1)).sum()
            gap = d[S].sum() - rhs
            if gap > worst[0] + 1e-12:
                worst = (gap, tuple(S))
    return worst[0] <= 1e-12, worst[0], worst[1]


def mincost_duals(C, U, d, cost_edge, deficit_cost):
    """Min-cost delivery with an expensive deficit edge (LP advance) per creditor.

    minimise sum_e c_e x_e + deficit_cost * sum_j s_j
    s.t.     sum_j x_vj <= C_v           (vault budget, dual lambda_v >= 0)
             x_vj <= U_vj                (edge capacity, dual mu_vj >= 0)
             sum_v x_vj + s_j = d_j      (demand, dual p_j)
    The capacity duals are the marginal value of one more unit of directional capacity on an
    edge: zero where the edge is slack, up to deficit_cost - c_e where it binds. They are
    planning prices under this fixed demand and cost model, not market prices.
    """
    C, U, d = np.asarray(C, float), np.asarray(U, float), np.asarray(d, float)
    V, J = U.shape
    edges = [(v, j) for v in range(V) for j in range(J) if U[v, j] > 0]
    n = len(edges)
    nx = n + J
    c = np.concatenate([[cost_edge] * n, [deficit_cost] * J])
    A_ub = lil_matrix((V + n, nx))
    b_ub = np.concatenate([C, [U[v, j] for v, j in edges]])
    for e, (v, j) in enumerate(edges):
        A_ub[v, e] = 1.0
        A_ub[V + e, e] = 1.0
    A_eq = lil_matrix((J, nx))
    for e, (v, j) in enumerate(edges):
        A_eq[j, e] = 1.0
    for j in range(J):
        A_eq[j, n + j] = 1.0
    res = linprog(c, A_ub=A_ub.tocsr(), b_ub=b_ub, A_eq=A_eq.tocsr(), b_eq=d, bounds=[(0, None)] * nx, method="highs")
    if res.status != 0:
        raise RuntimeError(res.message)
    marg = res.ineqlin.marginals  # <= 0 for minimisation: shadow price = -marginal
    vault_price = -marg[:V]
    edge_price = -marg[V:]
    return dict(cost=float(res.fun), deficit=float(res.x[n:].sum()), vault_price=vault_price,
                edge_price={edges[e]: float(edge_price[e]) for e in range(n)}, demand_price=res.eqlin.marginals.copy())
