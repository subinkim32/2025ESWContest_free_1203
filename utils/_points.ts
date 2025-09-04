// utils/points.ts
export type XY = { x: number; y: number };

export function toPts(pairs: [number, number][]) {
  return pairs.map(([x, y]) => ({ id: `(${x},${y})`, x, y }));
}

export function calFrom(pts: XY[], pad = 0) {
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  return { x0: minX - pad, x1: maxX + pad, y0: minY - pad, y1: maxY + pad };
}