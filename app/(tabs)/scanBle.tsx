// app/(tabs)/scanBle.tsx
import React, { useMemo } from "react";
import { View, Text, Button, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import { useBle } from "@/hooks/useBle";

const WS_URL = "ws://172.20.6.45:8000"; // IPv4 주소 수정
const EMA_ALPHA = 0.1;
const EMIT_MS = 200;

function fmtNum(v: number | null | undefined, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  try { return Number(v).toFixed(digits); } catch { return String(v); }
}

export default function ScanBleScreen() {
  const router = useRouter();

  const {
    ready,
    isScanning,
    latestList,
    currentFloor,
    startScan,
    stopScan,
  } = useBle({
    wsUrl: WS_URL,
    emaAlpha: EMA_ALPHA,
    emitIntervalMs: EMIT_MS,
    onFloorDetected: (floor) => {
      const path =
        floor === "B2" ? "/(tabs)/b2" :
        floor === "B1" ? "/(tabs)/b1" :
        floor === "1F" ? "/(tabs)/f1" :
                          "/(tabs)/f4";
      router.replace(path);
    },
  });

  const header = useMemo(() => {
    return `BLE Ready: ${ready}   |   Scanning: ${isScanning}   |   Floor: ${currentFloor ?? "-"}`;
  }, [ready, isScanning, currentFloor]);

  return (
    <View style={{ flex: 1, padding: 16 }}>
      <Text style={{ marginBottom: 8 }}>{header}</Text>

      <View style={{ flexDirection: "row", gap: 12, marginVertical: 12 }}>
        <Button title="Start Scan" onPress={startScan} disabled={!ready || isScanning} />
        <Button title="Stop Scan" onPress={stopScan} disabled={!isScanning} />
      </View>

      <ScrollView style={{ flex: 1 }}>
        {latestList.map((r) => (
          <Text key={`${r.floor}:${r.id}`} style={{ marginBottom: 6 }}>
            [{r.floor}] #{r.id} {r.name} | raw {fmtNum(r.rssi, 0)} | ema {fmtNum(r.filtered, 1)} | d {fmtNum(r.distance)} m
          </Text>
        ))}
        {latestList.length === 0 && (
          <Text style={{ opacity: 0.6 }}>스캔 결과가 아직 없습니다. Start Scan을 누르세요.</Text>
        )}
      </ScrollView>
    </View>
  );
}