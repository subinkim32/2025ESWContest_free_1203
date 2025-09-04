// components/FloorCalibratedMap.tsx
import { useAssets } from 'expo-asset';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ImageBackground, Platform, Pressable, StyleSheet, Text, View
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Polyline } from 'react-native-svg';
import { sendDeleteNode, sendRestoreGraph, sendRestoreNode } from '../config/ws';

export type Pt  = { id: string; x: number; y: number };
export type Cal = { x0: number; x1: number; y0: number; y1: number };

type Props = {
  image: any;
  points: Pt[];
  calInit: Cal;
  showDebugBorder?: boolean;
  current?: [number, number] | null;
  pathNodes?: Array<[number, number]> | null;
  floorKey: 'B2' | 'B1' | '1F' | '4F';
  tabBarPad?: number;
  pathColor?: string;
  hazardNodes?: Array<[number, number]>;
};

const DEFAULT_PATH_COLOR = '#2563EB';

export default function FloorCalibratedMap({
  tabBarPad = 0, image, points: initialPts, calInit, floorKey, showDebugBorder = false,
  current = null, pathNodes = null,   pathColor = DEFAULT_PATH_COLOR, hazardNodes = []
}: Props) {
  const insets = useSafeAreaInsets();

  const [assets] = useAssets([image]);
  const IMG_W = assets?.[0]?.width ?? 1000;
  const IMG_H = assets?.[0]?.height ?? 1000;

  const [points, setPoints] = useState(initialPts);
  const stackRef = useRef<Pt[]>([]);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [cal, _setCal] = useState(calInit);
  const [step, setStep] = useState(0.5);
  const [locked, setLocked] = useState(false);

  const setCalSafe = useCallback((next: Cal) => {
    let { x0, x1, y0, y1 } = next;
    if (x1 <= x0) x1 = x0 + 0.001;
    if (y1 <= y0) y1 = y0 + 0.001;
    _setCal({ x0, x1, y0, y1 });
  }, []);

  const content = useMemo(() => {
    if (!box.w || !box.h) return { offX: 0, offY: 0, drawW: 0, drawH: 0, scale: 1 };
    const scale = Math.min(box.w / IMG_W, box.h / IMG_H);
    const drawW = IMG_W * scale;
    const drawH = IMG_H * scale;
    const offX = (box.w - drawW) / 2;
    const offY = (box.h - drawH) / 2;
    return { offX, offY, drawW, drawH, scale };
  }, [box, IMG_W, IMG_H]);

  // CAD → 픽셀
  const toPixel = useCallback((p: Pt) => {
    const nx = (p.x - cal.x0) / (cal.x1 - cal.x0);
    const ny = (cal.y1 - p.y) / (cal.y1 - cal.y0); // y 반전
    return {
      left: content.offX + nx * content.drawW,
      top:  content.offY + ny * content.drawH,
    };
  }, [cal, content]);

  const toPixelXY = React.useCallback(
    (x: number, y: number) => {
      const { left, top } = toPixel({ x, y } as any);
      return { left: Math.round(left), top: Math.round(top) };
    },
    [toPixel]
  );
  
  const handlePressPoint = useCallback((id: string) => {
    // 로컬 삭제 + 스택 처리
    setPoints(prev => {
      const idx = prev.findIndex(p => p.id === id);
      if (idx < 0) return prev;
      const removed = prev[idx];
      stackRef.current.push(removed);
      const next = prev.slice();
      next.splice(idx, 1);
      return next;
    });

    // 서버로도 삭제 통지
    sendDeleteNode(floorKey, id);
  }, [floorKey, setPoints]);

  const undo = useCallback(() => {
    const last = stackRef.current.pop();
    if (last) setPoints(prev => [...prev, last]);

    // 간단 버전: 서버도 전체 원복(정확히 ‘되돌리기 1회’는 서버쪽에 별도 API 필요)
    if (last) sendRestoreNode(floorKey, last.id);
  }, [floorKey]);

  // 전체 복구
  const restoreAll = useCallback(() => {
    stackRef.current.length = 0;
    setPoints(initialPts);
    sendRestoreGraph(floorKey); // 서버 그래프 원복 + 서버가 경로 재계산해 다시 브로드캐스트
  }, [initialPts, floorKey]);

  // 포인트 크기 자동 스케일
    const pointSize = useMemo(
    () => Math.max(5, Math.min(12, content.drawW / 48)),
    [content.drawW]
    );
    const half = pointSize / 2;

  // 보정 조절
  const bump = (key: keyof Cal, delta: number) => {
    if (locked) return;
    setCalSafe({ ...cal, [key]: (cal[key] as number) + delta });
  };

    // 이미 있는 toPixel 이용
  const currentPix = useMemo(() => {
    if (!current) return null;
    const [x, y] = current;
    const { left, top } = toPixel({ id: 'cur', x, y });
    return { left, top };
  }, [current, toPixel]);

  // 경로 Polyline points 문자열
  const polyPoints = useMemo(() => {
    if (!pathNodes || pathNodes.length < 2) return '';
    return pathNodes
      .map(([x, y]) => {
        const { left, top } = toPixel({ id: '', x, y });
        return `${left},${top}`;
      })
      .join(' ');
  }, [pathNodes, toPixel]);

  return (
    <View
      style={styles.container}
      onLayout={e => {
        const { width, height } = e.nativeEvent.layout;
        setBox({ w: width, h: height });
      }}
    >
      <ImageBackground source={image} resizeMode="contain" style={{ flex: 1 }}>
        {showDebugBorder && (
          <View
            pointerEvents="none"
            style={{
              position:'absolute',
              left:content.offX, top:content.offY,
              width:content.drawW, height:content.drawH,
              borderWidth:1, borderColor:'rgba(0,150,255,0.5)'
            }}
          />
        )}

        {/* 파란 경로 (점들보다 뒤에 깔고, 터치 방해 X) */}
        {polyPoints ? (
          <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
            <Polyline
              points={polyPoints}
              stroke={pathColor}
              strokeWidth={3}
              fill="none"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </Svg>
        ) : null}

        <View style={styles.canvas}>
          {points.map(p => {
            const { left, top } = toPixel(p);
            return (
              <Pressable
                key={p.id}
                onPress={() => handlePressPoint(p.id)}
                style={[styles.pointWrap, { left, top }]}
                hitSlop={10}
                android_ripple={Platform.OS === 'android' ? { borderless: true } : undefined}
              >
                <View style={{
                  width: pointSize, height: pointSize, borderRadius: half,
                  marginLeft: -half, marginTop: -half,
                  backgroundColor:'rgba(76,175,80,0.9)', borderWidth:1, borderColor:'#2e7d32'
                }}/>
              </Pressable>
            );
          })}
        <View style={StyleSheet.absoluteFill} pointerEvents="none">
          {hazardNodes?.map(([x, y], i) => {
            const { left, top } = toPixelXY(x, y);
            return (
              <View
                key={`hz-${i}`}
                style={{
                  position: 'absolute',
                  left: left - 10,     // 지름 20 기준, 가운데 정렬
                  top:  top - 10,
                  width: 20, height: 20, borderRadius: 10,
                  backgroundColor: '#ef4444',
                  alignItems: 'center', justifyContent: 'center',
                }}
              >
                <Text style={{ color: '#fff', fontSize: 12 }}>🔥</Text>
              </View>
            );
          })}
        </View>
        {/* 현재 위치: 빨간 점 */}
        {currentPix && (
          <View
            pointerEvents="none"
            style={{
              position: 'absolute',
              left: currentPix.left,
              top: currentPix.top,
              width: 8,
              height: 8,
              marginLeft: -4,
              marginTop: -4,
              borderRadius: 4,
              backgroundColor: 'red',
              borderWidth: 1,
              borderColor: '#b71c1c',
            }}
          />
        )}
        </View>
      </ImageBackground>
      {/* 하단 툴바: 되돌리기 / 전체복구 */}
      <View style={[
        styles.toolbar,
        { bottom: 30 + insets.bottom + tabBarPad, zIndex: 20 }
      ]}>
        <Pressable style={styles.btn} onPress={undo}>
          <Text style={styles.btnText}>되돌리기</Text>
        </Pressable>
        <Pressable style={styles.btn} onPress={restoreAll}>
          <Text style={styles.btnText}>전체복구</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container:{ flex:1, backgroundColor:'#fff' },
  canvas:{ flex:1, position:'relative' },
  pointWrap:{ position:'absolute' },
  toolbar:{ position:'absolute', left:12, flexDirection:'row', gap:8 },
  btn:{ paddingHorizontal:12, paddingVertical:8, backgroundColor:'#111', borderRadius:8 },
  btnText:{ color:'#fff', fontWeight:'600' },
  calPanel:{ position:'absolute', right:8, backgroundColor:'rgba(255,255,255,0.92)', borderRadius:10, padding:8, gap:6 },
  calTxt:{ fontSize:12 },
  row:{ flexDirection:'row', gap:6 },
  smallBtn:{ paddingHorizontal:10, paddingVertical:8, backgroundColor:'#eee', borderRadius:8 },
});