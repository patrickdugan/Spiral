// Witness for the appendix on designed topologies: three small cubic bipartite polyhedral graphs, a
// Hamiltonian cycle avoiding each edge in turn found by exhaustive search, and the zero-net-flow property
// of a unit circulation round it. The cited theorem (Barnette's conjecture, as claimed in the OpenAI
// preprint of September 24, 2026) is about every graph in the class; this file checks three of them and
// proves nothing further. Planarity is not tested: each graph is the skeleton of a convex polyhedron.

export type Edge = [number, number];

export interface Graph {
  n: number;
  edges: Edge[];
  adj: number[][];
}

export function graphFromEdges(n: number, edges: Edge[]): Graph {
  const adj: number[][] = Array.from({ length: n }, () => []);
  for (const [u, v] of edges) {
    if (u === v || u < 0 || v < 0 || u >= n || v >= n) throw new Error(`bad edge ${u}-${v}`);
    adj[u]!.push(v);
    adj[v]!.push(u);
  }
  return { n, edges, adj };
}

/** Undirected edge key, so that {u,v} and {v,u} coincide. */
export function edgeKey(u: number, v: number): string {
  return u < v ? `${u}-${v}` : `${v}-${u}`;
}

/** The cube: 3-bit strings, adjacent when they differ in one bit. 8 vertices, 12 edges. */
export function cube(): Graph {
  const edges: Edge[] = [];
  for (let u = 0; u < 8; u++) for (const b of [1, 2, 4]) { const v = u ^ b; if (u < v) edges.push([u, v]); }
  return graphFromEdges(8, edges);
}

/** The hexagonal prism: two hexagons joined rung to rung. 12 vertices, 18 edges. */
export function hexagonalPrism(): Graph {
  const edges: Edge[] = [];
  for (let i = 0; i < 6; i++) {
    edges.push([i, (i + 1) % 6]);
    edges.push([6 + i, 6 + ((i + 1) % 6)]);
    edges.push([i, 6 + i]);
  }
  return graphFromEdges(12, edges);
}

/** The truncated octahedron: the 24 signed permutations of (0, 1, 2), adjacent at distance √2. 36 edges. */
export function truncatedOctahedron(): Graph {
  const perms = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
  const pts: number[][] = [];
  for (const p of perms) {
    for (const s1 of [1, -1]) {
      for (const s2 of [1, -1]) {
        const v = [p[0]!, p[1]!, p[2]!];
        let k = 0;
        for (let i = 0; i < 3; i++) if (v[i] !== 0) { v[i] = v[i]! * (k === 0 ? s1 : s2); k++; }
        pts.push(v);
      }
    }
  }
  const edges: Edge[] = [];
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      const d2 = pts[i]!.reduce((s, c, k) => s + (c - pts[j]![k]!) ** 2, 0);
      if (d2 === 2) edges.push([i, j]);
    }
  }
  return graphFromEdges(24, edges);
}

export function isCubic(g: Graph): boolean {
  return g.adj.every((a) => a.length === 3);
}

export function isBipartite(g: Graph): boolean {
  const color = new Array<number>(g.n).fill(-1);
  for (let s = 0; s < g.n; s++) {
    if (color[s] !== -1) continue;
    color[s] = 0;
    const queue = [s];
    while (queue.length) {
      const u = queue.shift()!;
      for (const v of g.adj[u]!) {
        if (color[v] === -1) { color[v] = 1 - color[u]!; queue.push(v); }
        else if (color[v] === color[u]) return false;
      }
    }
  }
  return true;
}

function connectedWithout(g: Graph, removed: Set<number>): boolean {
  const start = [...Array(g.n).keys()].find((v) => !removed.has(v));
  if (start === undefined) return false;
  const seen = new Set<number>([start]);
  const stack = [start];
  while (stack.length) {
    const u = stack.pop()!;
    for (const v of g.adj[u]!) if (!removed.has(v) && !seen.has(v)) { seen.add(v); stack.push(v); }
  }
  return seen.size === g.n - removed.size;
}

/** At least four vertices, and deleting any set of at most two vertices leaves a connected graph. */
export function isThreeVertexConnected(g: Graph): boolean {
  if (g.n < 4) return false;
  if (!connectedWithout(g, new Set())) return false;
  for (let a = 0; a < g.n; a++) {
    if (!connectedWithout(g, new Set([a]))) return false;
    for (let b = a + 1; b < g.n; b++) if (!connectedWithout(g, new Set([a, b]))) return false;
  }
  return true;
}

/**
 * A Hamiltonian cycle that does not use the edge `avoid` (or any cycle when `avoid` is null), as a vertex
 * sequence starting at 0, found by depth-first search; null if none exists. Exhaustive on these sizes.
 */
export function hamiltonianCycleAvoiding(g: Graph, avoid: Edge | null): number[] | null {
  const forbidden = avoid === null ? "" : edgeKey(avoid[0], avoid[1]);
  const start = 0;
  const path = [start];
  const seen = new Array<boolean>(g.n).fill(false);
  seen[start] = true;
  const rec = (u: number): boolean => {
    if (path.length === g.n) return g.adj[u]!.includes(start) && edgeKey(u, start) !== forbidden;
    for (const v of g.adj[u]!) {
      if (seen[v] || edgeKey(u, v) === forbidden) continue;
      seen[v] = true; path.push(v);
      if (rec(v)) return true;
      path.pop(); seen[v] = false;
    }
    return false;
  };
  return rec(start) ? path.slice() : null;
}

/**
 * A unit payment from each vertex of the cycle to its successor. Returns each vertex's net position
 * (received minus paid) and, per edge the cycle uses, the unit moved from the upstream side to the
 * downstream side, signed +1 when it moves from the lower-numbered endpoint to the higher. Edges the
 * cycle does not use are absent: nothing moves on them.
 */
export function unitCirculation(g: Graph, cycle: number[]): { net: number[]; shift: Map<string, number> } {
  const net = new Array<number>(g.n).fill(0);
  const shift = new Map<string, number>();
  for (let i = 0; i < cycle.length; i++) {
    const u = cycle[i]!, v = cycle[(i + 1) % cycle.length]!;
    if (!g.adj[u]!.includes(v)) throw new Error(`not an edge: ${u}-${v}`);
    net[u] -= 1; net[v] += 1;
    shift.set(edgeKey(u, v), (shift.get(edgeKey(u, v)) ?? 0) + (u < v ? 1 : -1));
  }
  return { net, shift };
}
