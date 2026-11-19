export type Entity = {
  id: string; name: string; entity_type: string; description?: string;
  aliases?: string[]; memory_count: number; relation_count?: number;
};
export type Relation = {
  id: string; from_entity_id: string; to_entity_id: string;
  relation_type: string; confidence: number;
};
export type Graph = { nodes: Entity[]; edges: Relation[] };
export type Point = { x: number; y: number };

export const typeColours: Record<string, string> = {
  person: '#ffbd7a', server: '#70e0ff', device: '#7fa8ff', project: '#b6ff4a',
  company: '#d5a2ff', software: '#a4b8ff', place: '#79dbc0',
  organisation: '#f1a7d2', concept: '#f0d77c', other: '#a1aab8',
};
export const entityColour = (type: string) => typeColours[type] || typeColours.other;
export const nodeRadius = (node: Entity) => 13 + Math.min(12, Math.sqrt(Math.max(0, node.memory_count)) * 2);
export const matchesEntity = (entity: Entity, query: string) =>
  [entity.name, entity.description || '', ...(entity.aliases || [])].join(' ').toLowerCase().includes(query.trim().toLowerCase());

/** Filters never introduce edges whose endpoints are outside the visible map. */
export function filterGraph(graph: Graph, query: string, type: string, confidence: number, focusId = ''): Graph {
  const candidates = graph.nodes.filter(n => !type || n.entity_type === type);
  const candidateIds = new Set(candidates.map(n => n.id));
  const edges = graph.edges.filter(e => e.confidence >= confidence && candidateIds.has(e.from_entity_id) && candidateIds.has(e.to_entity_id));
  let ids = candidateIds;
  if (query.trim() || focusId) {
    const matches = new Set(candidates.filter(n => focusId ? n.id === focusId : matchesEntity(n, query)).map(n => n.id));
    ids = new Set(matches);
    for (const edge of edges) {
      if (matches.has(edge.from_entity_id) || matches.has(edge.to_entity_id)) {
        ids.add(edge.from_entity_id); ids.add(edge.to_entity_id);
      }
    }
  }
  return { nodes: candidates.filter(n => ids.has(n.id)), edges: edges.filter(e => ids.has(e.from_entity_id) && ids.has(e.to_entity_id)) };
}

/** Deterministic, bounded force layout. Calculated once per dataset, never animated. */
export function layoutGraph(graph: Graph): Map<string, Point> {
  const nodes = [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id));
  const index = new Map(nodes.map((n, i) => [n.id, i]));
  const links = graph.edges.filter(e => e.from_entity_id !== e.to_entity_id && index.has(e.from_entity_id) && index.has(e.to_entity_id))
    .sort((a, b) => a.id.localeCompare(b.id));
  const degree = new Map<string, number>();
  for (const edge of links) {
    degree.set(edge.from_entity_id, (degree.get(edge.from_entity_id) || 0) + 1);
    degree.set(edge.to_entity_id, (degree.get(edge.to_entity_id) || 0) + 1);
  }
  const positions = nodes.map((_, i) => {
    const angle = i * 2.399963229728653;
    const radius = Math.sqrt((i + .5) / Math.max(1, nodes.length)) * 270;
    return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
  });
  for (let step = 0; step < 220; step++) {
    const forces = nodes.map(() => ({ x: 0, y: 0 }));
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = positions[i].x - positions[j].x, dy = positions[i].y - positions[j].y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const clearance = nodeRadius(nodes[i]) + nodeRadius(nodes[j]) + 26;
        const force = 1500 / (distance * distance) + Math.max(0, clearance - distance) * .65;
        const x = dx / distance * force, y = dy / distance * force;
        forces[i].x += x; forces[i].y += y; forces[j].x -= x; forces[j].y -= y;
      }
    }
    for (const edge of links) {
      const a = index.get(edge.from_entity_id)!, b = index.get(edge.to_entity_id)!;
      const dx = positions[b].x - positions[a].x, dy = positions[b].y - positions[a].y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      // Dense hubs and repeated relationships should not collapse their neighbours.
      const strength = .09 / Math.sqrt(Math.min(degree.get(edge.from_entity_id)!, degree.get(edge.to_entity_id)!));
      const force = (distance - 90) * strength;
      const x = dx / distance * force, y = dy / distance * force;
      forces[a].x += x; forces[a].y += y; forces[b].x -= x; forces[b].y -= y;
    }
    const cooling = 1 - step / 260;
    positions.forEach((p, i) => {
      p.x += Math.max(-8, Math.min(8, forces[i].x - p.x * .002)) * cooling;
      p.y += Math.max(-8, Math.min(8, forces[i].y - p.y * .002)) * cooling;
    });
  }
  return new Map(nodes.map((node, i) => [node.id, positions[i]]));
}

/** Room for node labels is included when fitting both wide and narrow screens. */
export function graphBounds(nodes: Entity[], positions: Map<string, Point>) {
  if (!nodes.length) return { x: -400, y: -280, width: 800, height: 560 };
  const points = nodes.map(n => positions.get(n.id)).filter((p): p is Point => !!p);
  if (!points.length) return { x: -400, y: -280, width: 800, height: 560 };
  const left = Math.min(...points.map(p => p.x)) - 100, top = Math.min(...points.map(p => p.y)) - 65;
  return { x: left, y: top, width: Math.max(220, Math.max(...points.map(p => p.x)) + 100 - left), height: Math.max(180, Math.max(...points.map(p => p.y)) + 65 - top) };
}
