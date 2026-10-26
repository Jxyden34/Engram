"use client";
import { CSSProperties, PointerEvent, useId, useMemo, useRef, useState } from "react";
import { Graph, Point, entityColour, graphBounds, matchesEntity, nodeRadius } from "@/lib/graph";

export default function NetworkMap({ graph, positions, selectedId, query, allLabels, onSelect, onClear }: {
  graph: Graph; positions: Map<string, Point>; selectedId: string; query: string; allLabels: boolean;
  onSelect: (id: string) => void; onClear: () => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState("");
  const [panning, setPanning] = useState(false);
  const drag = useRef<{ id: number; x: number; y: number; pan: Point; moved: boolean } | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const marker = useId().replaceAll(":", "");
  const bounds = graphBounds(graph.nodes, positions);
  const width = bounds.width / zoom, height = bounds.height / zoom;
  const view = { x: bounds.x + (bounds.width - width) / 2 + pan.x, y: bounds.y + (bounds.height - height) / 2 + pan.y };
  const active = hovered || selectedId;
  const neighbours = useMemo(() => {
    const ids = new Set([active]);
    graph.edges.forEach(e => { if (e.from_entity_id === active) ids.add(e.to_entity_id); if (e.to_entity_id === active) ids.add(e.from_entity_id); });
    return ids;
  }, [graph.edges, active]);
  const prominent = useMemo(() => new Set([...graph.nodes].sort((a, b) => (b.relation_count || 0) + b.memory_count - (a.relation_count || 0) - a.memory_count).slice(0, 10).map(n => n.id)), [graph.nodes]);
  const hasActive = graph.nodes.some(n => n.id === active);
  const labelledEdges = new Set(graph.edges.filter(e => e.from_entity_id === active || e.to_entity_id === active).sort((a, b) => b.confidence - a.confidence).slice(0, 6).map(e => e.id));
  function fit() { setZoom(1); setPan({ x: 0, y: 0 }); }
  // Filtering retains node coordinates but fits the newly visible neighbourhood.
  const scope = graph.nodes.map(n => n.id).join(",");
  const [lastScope, setLastScope] = useState(scope);
  if (lastScope !== scope) { setLastScope(scope); setZoom(1); setPan({ x: 0, y: 0 }); }

  function point(event: PointerEvent<SVGSVGElement>) {
    const matrix = svg.current?.getScreenCTM();
    return matrix ? new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse()) : null;
  }
  function down(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0 || (event.target as Element).closest("[data-entity]")) return;
    const p = point(event); if (!p) return;
    drag.current = { id: event.pointerId, x: p.x, y: p.y, pan: { ...pan }, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId); setPanning(true);
  }
  function move(event: PointerEvent<SVGSVGElement>) {
    const d = drag.current; if (!d || d.id !== event.pointerId) return;
    const p = point(event); if (!p) return;
    // Remove the changed viewBox origin from the pointer's world coordinates.
    const dx = p.x - d.x - pan.x + d.pan.x, dy = p.y - d.y - pan.y + d.pan.y;
    if (Math.hypot(dx, dy) > 2) d.moved = true;
    setPan({ x: d.pan.x - dx, y: d.pan.y - dy });
  }
  function up(event: PointerEvent<SVGSVGElement>) {
    const d = drag.current; if (!d || d.id !== event.pointerId) return;
    if (!d.moved && event.type !== "pointercancel") onClear();
    drag.current = null; setPanning(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return <div className="networkCanvas">
    <svg ref={svg} viewBox={`${view.x} ${view.y} ${width} ${height}`} role="group" aria-label="Interactive memory graph. Tab to entities, then press Enter to inspect. Drag the background to pan."
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onLostPointerCapture={() => { drag.current = null; setPanning(false); }}
      className={panning ? "isPanning" : ""} onKeyDown={e => { if (e.key === "Escape") { setHovered(""); onClear(); } }}>
      <defs><marker id={marker} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 8 4 L 0 8 z" fill="#a2aebe" /></marker></defs>
      {graph.edges.map(edge => {
        const a = positions.get(edge.from_entity_id), b = positions.get(edge.to_entity_id);
        if (!a || !b || edge.from_entity_id === edge.to_entity_id) return null;
        const lit = hasActive && (edge.from_entity_id === active || edge.to_entity_id === active);
        const target = graph.nodes.find(n => n.id === edge.to_entity_id)!;
        const distance = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y));
        const inset = Math.min(.45, (nodeRadius(target) + 5) / distance);
        return <g key={edge.id} className={`networkEdge${lit ? " isHighlighted" : hasActive ? " isDimmed" : ""}`}>
          <line x1={a.x} y1={a.y} x2={b.x - (b.x - a.x) * inset} y2={b.y - (b.y - a.y) * inset} markerEnd={lit ? `url(#${marker})` : undefined} />
          {lit && labelledEdges.has(edge.id) && (zoom >= 1.4 || graph.nodes.length <= 18) && <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 7} textAnchor="middle">{edge.relation_type.replaceAll("_", " ")}</text>}
        </g>;
      })}
      {graph.nodes.map(node => {
        const p = positions.get(node.id); if (!p) return null;
        const radius = nodeRadius(node), connected = !hasActive || neighbours.has(node.id);
        const matched = !!query.trim() && matchesEntity(node, query);
        const showLabel = allLabels || graph.nodes.length <= 18 || node.id === active || (hasActive && connected && prominent.has(node.id)) || matched || (!hasActive && prominent.has(node.id));
        return <g data-entity={node.id} key={node.id} role="button" tabIndex={0} aria-pressed={selectedId === node.id}
          aria-label={`${node.name}, ${node.entity_type}, ${node.memory_count} linked memories`} className={`networkNode${connected ? "" : " isDimmed"}${node.id === selectedId ? " isSelected" : ""}`}
          style={{ "--node-colour": entityColour(node.entity_type) } as CSSProperties}
          transform={`translate(${p.x},${p.y})`} onClick={() => onSelect(node.id)} onMouseEnter={() => setHovered(node.id)} onMouseLeave={() => setHovered("")}
          onFocus={() => setHovered(node.id)} onBlur={() => setHovered("")}
          onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(node.id); } }}>
          <title>{node.name} · {node.entity_type} · {node.memory_count} linked memories</title>
          <circle className="networkHit" r={Math.max(22, radius + 6)} /><circle className="networkHalo" r={radius + 6} />
          <circle className="networkDot" r={radius} /><text className="networkInitial" textAnchor="middle" y="4">{node.name.trim().slice(0, 2).toUpperCase()}</text>
          {showLabel && <text className="networkLabel" textAnchor="middle" y={radius + 18}>{node.name.length > 24 ? `${node.name.slice(0, 23)}…` : node.name}</text>}
        </g>;
      })}
    </svg>
    <div className="networkHelp">Drag to explore · select to inspect</div>
    <div className="networkControls" aria-label="Map view controls"><button aria-label="Zoom out" disabled={zoom <= .5} onClick={() => setZoom(v => Math.max(.5, v / 1.3))}>−</button><output aria-label="Zoom level">{Math.round(zoom * 100)}%</output><button aria-label="Zoom in" disabled={zoom >= 4} onClick={() => setZoom(v => Math.min(4, v * 1.3))}>+</button><button onClick={fit}>Fit map</button></div>
  </div>;
}
