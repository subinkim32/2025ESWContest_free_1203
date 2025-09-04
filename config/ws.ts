// config/ws.ts
import Constants from 'expo-constants';

function getHostFromExpo(): string {
  const hostUri =
    Constants.expoConfig?.hostUri ||
    Constants.manifest2?.extra?.expoGo?.developer?.host || 
    '';
  const host = hostUri.split(':')[0];
  return host || '172.20.6.45'; // 최후의 fallback
}

export const WS_PORT = 8000;
export const WS_URL = 'ws://172.20.6.45:8000'; // IPv4 주소 수정

type Msg = any;

let ws: WebSocket | null = null;
let isOpen = false;
const queue: string[] = [];
const listeners: Array<(msg: Msg) => void> = [];

type FloorKey = 'B2' | 'B1' | '1F' | '4F';
type XY = [number, number];

const hazardByFloor: Record<FloorKey, XY[]> = {
  B2: [], B1: [], '1F': [], '4F': []
};

// 전용 리스너(이름 충돌 방지)
type HazardEvent = { type: 'hazard'; floor: FloorKey; hazardNodes: XY[] };
type HazardListener = (ev: HazardEvent) => void;
const hazardListeners = new Set<HazardListener>();

export const onHazardUpdate = (fn: HazardListener) => {
  hazardListeners.add(fn);
  return () => hazardListeners.delete(fn);
};

const notifyHazard = (floor: FloorKey) => {
  const nodes = hazardByFloor[floor] ?? [];
  hazardListeners.forEach(fn => fn({ type: 'hazard', floor, hazardNodes: nodes }));
};

export const getHazards = (floor: FloorKey) => hazardByFloor[floor] ?? [];

function setHandlers(sock: WebSocket) {
  sock.onopen = () => {
    isOpen = true;
    // 대기열 비우기
    while (queue.length) {
      const t = queue.shift()!;
      try { sock.send(t); } catch {}
    }
    console.log('[WS] opened:', WS_URL);
  };

  sock.onmessage = (e) => {
    try {
      const msg = JSON.parse(String(e.data));
      listeners.forEach(fn => fn(msg));
    } catch {
      listeners.forEach(fn => fn(e.data));
    }
  };

  sock.onclose = () => {
    isOpen = false;
    console.log('[WS] closed, retrying in 2s');
    setTimeout(() => {
      // 자동 재연결
      try { ensureWS(); } catch {}
    }, 2000);
  };

  sock.onerror = (e) => {
    console.warn('[WS] error', e);
  };
}

export function ensureWS(): WebSocket {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return ws;
  }
  ws = new WebSocket(WS_URL);
  setHandlers(ws);
  return ws;
}

// 공용 메시지 수신 구독
export function wsOnMessage(fn: (msg: Msg) => void) {
  listeners.push(fn);
  return () => {
    const i = listeners.indexOf(fn);
    if (i >= 0) listeners.splice(i, 1);
  };
}

// JSON 발송
export function wsSend(obj: any) {
  const text = typeof obj === 'string' ? obj : JSON.stringify(obj);
  const sock = ensureWS();
  if (isOpen && sock.readyState === WebSocket.OPEN) {
    sock.send(text);
  } else {
    queue.push(text);
  }
}

// 앱에서 쓰기 편한 헬퍼들
export function sendDeleteNode(floor: string, nodeId: string) {
  wsSend({ kind: 'delete_node', floor, node: nodeId });
}

export function sendRestoreGraph(floor: string) { //전체 복원
  wsSend({ kind: 'restore_graph', floor });
}

export function sendRestoreNode(floor: string, nodeId: string) { //각 노드 복원
  wsSend({ kind: 'restore_node', floor, node: nodeId });
}