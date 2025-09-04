// hooks/useBle.ts
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Platform, PermissionsAndroid } from "react-native";
import { BleManager, Device } from "react-native-ble-plx";

// ====== Constants / Helpers ======
const FLOOR_ALIAS: Record<string, string> = {
  B2: "B2", B1: "B1", F1: "1F", "1F": "1F", F4: "4F", "4F": "4F", BF2: "B2", BF1: "B1",
};
const BEACON_NAME_RE = /^\s*([A-Za-z0-9]+)[_](\d+)\s*$/;
const DEFAULT_WS = "ws://172.20.6.45:8000";
const OUTLIER_MIN = -99; // drop RSSI BEFORE EMA

type FloorKey = "B2" | "B1" | "1F" | "4F";

type Reading = {
  id: number;
  name: string;
  floor: FloorKey;
  rssi: number | null;
  filtered: number | null;
  distance?: number;
};

type EMAState = { filtered: number | null; ts: number };

type UseBleOptions = {
  wsUrl?: string;
  emaAlpha?: number;          // 0.1
  emitIntervalMs?: number;    // 200ms
  onFloorDetected?: (floor: FloorKey) => void;
};

function normalizeFloorToken(token?: string | null): FloorKey | any {
  const t = (token ?? "").trim().toUpperCase();
  return (FLOOR_ALIAS as any)[t] ?? t;
}

function parseBeaconName(name?: string | null): { floor: FloorKey; bid: number } | null {
  if (!name) return null;
  const m = BEACON_NAME_RE.exec(name);
  if (!m) return null;
  const floor = normalizeFloorToken(m[1]) as FloorKey;
  const bid = Number(m[2]);
  if (!floor || Number.isNaN(bid)) return null;
  return { floor, bid };
}

// Placeholder calibration
function rssiToMeters(rssi: number): number {
  const txPower = -59;
  const n = 2.0;
  return Math.pow(10, (txPower - rssi) / (10 * n));
}

function isOutlier(v: number | null | undefined): boolean {
  if (v == null) return true;
  if (!Number.isFinite(v)) return true;
  if (v === 127) return true;
  return v <= OUTLIER_MIN;
}

// ====== Hook ======
export function useBle(opts?: UseBleOptions) {
  const {
    wsUrl = DEFAULT_WS,
    emaAlpha = 0.1,
    emitIntervalMs = 100,
    onFloorDetected,
  } = opts ?? {};

  const managerRef = useRef(new BleManager());
  const wsRef = useRef<WebSocket | null>(null);

  const [ready, setReady] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [currentFloor, setCurrentFloor] = useState<FloorKey | null>(null);

  // latest map & EMA state
  const latestMap = useRef<Map<number, Reading>>(new Map());
  const emaMap   = useRef<Map<number, EMAState>>(new Map());

  // ====== WS ======
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;

    function connect() {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => {/* no-op */};
      ws.onerror = () => {/* no-op */};
      ws.onclose = () => {
        wsRef.current = null;
        if (!closed) setTimeout(connect, 1000);
      };
      ws.onmessage = () => {/* ignore */};
    }
    connect();

    return () => {
      closed = true;
      try { ws?.close(); } catch {}
      wsRef.current = null;
    };
  }, [wsUrl]);

  // ====== Android ======
  useEffect(() => {
    async function prepare() {
      if (Platform.OS === "android") {
        try {
          const perms = [
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.BLUETOOTH_SCAN",
            "android.permission.BLUETOOTH_CONNECT",
          ] as const;
          for (const p of perms) {
            await PermissionsAndroid.request(p);
          }
        } catch {}
      }
      setReady(true);
    }
    prepare();
    return () => {
      try { managerRef.current.destroy(); } catch {}
    };
  }, []);

  // ====== Core RSSI handler ======
  const handleRssiSample = useCallback((dev: Device, rssi: number | null) => {
    const info = parseBeaconName(dev.name ?? dev.localName);
    if (!info) return;
    const floor = info.floor as FloorKey;
    const id = info.bid;
    const name = `${floor}_${id}`;

    
    // DROP OUTLIERS 먼저 -> 그 후 EMA
    if (isOutlier(rssi)) {
      const prev = emaMap.current.get(id)?.filtered ?? null;

      latestMap.current.set(id, {
        id, name, floor,
        rssi: rssi ?? null,           // keep raw for UI/debug
        filtered: prev,               // EMA not updated
        distance: prev == null ? undefined : rssiToMeters(prev),
      });
      return;
    }

    const prev = emaMap.current.get(id)?.filtered ?? null;
    const alpha = emaAlpha;
    const filtered = (prev == null) ? (rssi as number) : (alpha * (rssi as number) + (1 - alpha) * prev);
    emaMap.current.set(id, { filtered, ts: Date.now() });

    latestMap.current.set(id, {
      id, name, floor,
      rssi: rssi as number,
      filtered,
      distance: rssiToMeters(filtered),
    });

    if (floor !== currentFloor) {
      setCurrentFloor(floor);
      onFloorDetected?.(floor);
    }
  }, [emaAlpha, currentFloor, onFloorDetected]);

  // ====== BLE scan control ======
  const startScan = useCallback(() => {
    if (!ready || isScanning) return;

    setIsScanning(true);
    managerRef.current.startDeviceScan(null, { allowDuplicates: true }, (error, device) => {
      if (error) {
        console.warn("[BLE] scan error", error);
        return;
      }
      if (!device) return;
      handleRssiSample(device, device.rssi ?? null);
    });
  }, [ready, isScanning, handleRssiSample]);

  const stopScan = useCallback(() => {
    if (!isScanning) return;
    try { managerRef.current.stopDeviceScan(); } catch {}
    setIsScanning(false);
  }, [isScanning]);

  useEffect(() => {
    if (!ready) return;
    const t = setInterval(() => {
      const list: Array<{id: number; filtered: number | null; rssi: number | null}> = [];
      latestMap.current.forEach((v) => {
        list.push({ id: v.id, filtered: v.filtered, rssi: v.rssi });
      });
      list.sort((a, b) => a.id - b.id);

      const msg = {
        kind: "ble_readings",
        floor: currentFloor ?? "B2",
        list,
      };
      const ws = wsRef.current;
      if (ws && ws.readyState === 1) {
        try { ws.send(JSON.stringify(msg)); } catch {}
      }
    }, emitIntervalMs);
    return () => clearInterval(t);
  }, [ready, emitIntervalMs, currentFloor]);

  const latestList: Reading[] = useMemo(() => {
    return Array.from(latestMap.current.values())
      .sort((a, b) => {
        if (a.floor !== b.floor) return a.floor.localeCompare(b.floor);
        return a.id - b.id;
      });
  }, [currentFloor, isScanning]);

  return {
    ready,
    isScanning,
    latestList,
    currentFloor,
    startScan,
    stopScan,
  };
}