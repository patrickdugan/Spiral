import { test } from "node:test";
import assert from "node:assert/strict";
import {
  cube, hexagonalPrism, truncatedOctahedron, isCubic, isBipartite, isThreeVertexConnected,
  hamiltonianCycleAvoiding, unitCirculation, edgeKey, type Graph,
} from "./hamiltonian.ts";

test("Appendix on designed topologies: on three cubic bipartite polyhedral graphs a Hamiltonian cycle avoiding each edge exists, and a unit circulation round it nets to zero at every participant and moves one unit on every cycle channel and nothing elsewhere", () => {
  const graphs: Array<[string, Graph]> = [["cube", cube()], ["hexagonal prism", hexagonalPrism()], ["truncated octahedron", truncatedOctahedron()]];
  for (const [name, g] of graphs) {
    // The class the theorem is about, less planarity, which holds because each is a convex polyhedron's skeleton.
    assert.ok(isCubic(g), `${name} is cubic`);
    assert.ok(isBipartite(g), `${name} is bipartite`);
    assert.ok(isThreeVertexConnected(g), `${name} is 3-vertex-connected`);
    assert.equal(g.edges.length, (3 * g.n) / 2, `${name} has 3n/2 edges`);
    for (const e of g.edges) {
      const cycle = hamiltonianCycleAvoiding(g, e);
      assert.ok(cycle !== null, `${name}: no Hamiltonian cycle avoiding edge ${e[0]}-${e[1]}`);
      assert.equal(cycle.length, g.n);
      assert.equal(new Set(cycle).size, g.n, `${name}: cycle repeats a vertex`);
      const { net, shift } = unitCirculation(g, cycle);
      assert.ok(net.every((x) => x === 0), `${name}: the circulation changed a net position`);
      assert.equal(shift.size, g.n, `${name}: a cycle of n vertices uses n edges`);
      assert.ok(!shift.has(edgeKey(e[0], e[1])), `${name}: the avoided edge carried flow`);
      for (const v of shift.values()) assert.equal(Math.abs(v), 1);
    }
  }
  // The search is exhaustive, so it also says when no cycle exists: a graph outside the class.
  const k23: Graph = { n: 5, edges: [[0, 2], [0, 3], [0, 4], [1, 2], [1, 3], [1, 4]], adj: [] };
  for (let i = 0; i < 5; i++) k23.adj.push([]);
  for (const [u, v] of k23.edges) { k23.adj[u]!.push(v); k23.adj[v]!.push(u); }
  assert.equal(hamiltonianCycleAvoiding(k23, null), null, "K_{2,3} is bipartite and not Hamiltonian; the search reports it");
});
