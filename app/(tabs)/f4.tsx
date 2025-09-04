// f4.tsx 
import { useBottomTabBarHeight } from '@react-navigation/bottom-tabs';
import React, { useEffect, useRef, useState } from 'react';
import { Alert, Platform, Pressable, StyleSheet, Text, Vibration, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import FireBanner, { BANNER_HEIGHT } from '../../components/FireBanner';
import FloorCalibratedMap from '../../components/FloorCalibratedMap';
import ImageOverlay from '../../components/ImageOverlay';
import SafetyOverlay from '../../components/SafetyOverlay';

import { ensureWS, wsOnMessage } from '../../config/ws';
import { toPts } from '../../utils/_points';

// ===== 배경도면/이미지 =====
const IMG = require('../../assets/images/F4(문자X, 아이콘O).png');
const APP_GUIDE_SRC = require('../../assets/images/app_guide.png');
const FIRE_ESCAPE_IMG = require('../../assets/images/fire_escape.jpg');     
const EXTINGUISHER_IMG = require('../../assets/images/fire_use.jpg');     

// ===== 경로 노드 (4F) =====
const raw: [number,number][] = [
  [-6,-3], [-2,1], [-2,5], [-2,9], [2,1], [6,1], [10,1], [14,1], [18,1],
];
const POINTS = toPts(raw);

// ===== 화면 보정 초기값 =====
const CAL_INIT = { x0: -32.0, x1: 52.5, y0: -38.0, y1: 39.0 };

// ===== 타입 =====
type XY = [number, number];
type FireAlertMsg = {
  kind: 'fire_alert';
  floor: string;
  confidence: number;
  ts?: string;
  image?: string;
};

export default function F4Screen() {
  const insets = useSafeAreaInsets();
  const pad = useBottomTabBarHeight();

  const [showBanner, setShowBanner] = useState(false);
  const bannerText = '🔥 화재 감지(4F)';
  const topPad = showBanner ? (insets.top + 8 + BANNER_HEIGHT + 8) : insets.top;

  const [showSafety, setShowSafety] = useState(false);
  const [showAppGuide, setShowAppGuide] = useState(false);

  const [current, setCurrent] = useState<XY | null>(null);
  const [pathNodes, setPathNodes] = useState<XY[]>([]);
  const [hazards, setHazards] = useState<XY[]>([]);

  const [fireAlert, setFireAlert] = useState<FireAlertMsg | null>(null);
  const lastFireMsRef = useRef(0);
  const COOLDOWN_MS = 3000;

  useEffect(() => {
    // 공용 소켓 보장(없으면 생성, 끊기면 재연결)
    ensureWS();

    // 모든 메시지 구독
    const off = wsOnMessage((msg: any) => {
      // 1) 위치/경로 갱신
      if (String(msg.floor || '').toUpperCase() === '4F') {
        const snap = Array.isArray(msg.snapped_list) ? msg.snapped_list : [];
        if (snap.length && Array.isArray(snap[0]) && snap[0].length === 2) {
          setCurrent([Number(snap[0][0]), Number(snap[0][1])]);
        }
        if (Array.isArray(msg.best_path)) {
          const cleaned: XY[] = msg.best_path
            .filter((p: any) => Array.isArray(p) && p.length === 2)
            .map((p: any) => [Number(p[0]), Number(p[1])] as XY);
          setPathNodes(cleaned);
        }
      }

      // 2) 🔥 화재 알림
      if (msg?.kind === 'fire_alert' && String(msg.floor || '').toUpperCase() === '4F') {
        const now = Date.now();
        if (now - lastFireMsRef.current < COOLDOWN_MS) return; // 너무 자주 뜨는 것 방지
        lastFireMsRef.current = now;

        const alertMsg: FireAlertMsg = {
          kind: 'fire_alert',
          floor: '4F',
          confidence: Number(msg.confidence ?? 0),
          ts: msg.ts,
          image: typeof msg.image === 'string' ? msg.image : undefined,
        };
        setFireAlert(alertMsg);

        try { Vibration.vibrate(500); } catch {}
        setShowSafety(true);

        if (Platform.OS !== 'web') {
          Alert.alert('화재 감지', `4F층에 화재가 발생했습니다.\n신속히 대피하세요!`);
        }
      }

      // 3-a) 개별 이벤트 형식: { kind:'hazard', floor, node:[x,y], active:true/false }
      if (msg.kind === 'hazard' && String(msg.floor || '').toUpperCase() === '4F'
          && Array.isArray(msg.node) && msg.node.length === 2) {
        const xy: XY = [Number(msg.node[0]), Number(msg.node[1])];
        setHazards(prev => msg.active === false
          ? prev.filter(([x, y]) => !(x === xy[0] && y === xy[1]))
          : (prev.some(([x, y]) => x === xy[0] && y === xy[1]) ? prev : [...prev, xy]));
      }

      // 3-b) 상태 스냅샷 형식: { kind:'hazard_state', floor:'4F', hazard_nodes:[[x,y], ...] }
      if (msg.kind === 'hazard_state'
          && String(msg.floor || '').toUpperCase() === '4F'
          && Array.isArray(msg.hazard_nodes)) {
        const list: XY[] = (msg.hazard_nodes as any[])
          .filter((p: any) => Array.isArray(p) && p.length === 2)
          .map((p: any) => [Number(p[0]), Number(p[1])] as XY);
        setHazards(list);
      }
    });

    return () => off();
  }, []);

  return (
    <View style={[styles.screen, { paddingTop: topPad }]}>
      {/* 상단 화재 배너 (absolute) */}
      <FireBanner
        visible={showBanner}
        text={bannerText}
        onPressGuide={() => setShowSafety(true)}
        onClose={() => setShowBanner(false)}
      />

      {/* 지도 + 아이콘/경로 */}
      <FloorCalibratedMap
        image={IMG}
        points={POINTS}
        calInit={CAL_INIT}
        current={current}
        pathNodes={pathNodes}
        floorKey="4F"
        tabBarPad={pad}
        hazardNodes={hazards}      
        pathColor="#2563EB"
      />

      {/* 실시간 화재 알림 미니 배너 */}
      {fireAlert && (
        <View style={styles.banner}>
          <Text style={styles.bannerTxt}>
            🔥 화재 감지(4F) conf={fireAlert.confidence.toFixed(2)}
          </Text>
          <Pressable onPress={() => setShowSafety(true)} style={styles.bannerBtn}>
            <Text style={styles.bannerBtnTxt}>안내 보기</Text>
          </Pressable>
          <Pressable onPress={() => setFireAlert(null)} style={styles.bannerClose}>
            <Text style={styles.bannerBtnTxt}>닫기</Text>
          </Pressable>
        </View>
      )}

      {/* 하단 오른쪽 두 개 버튼 */}
      <View style={[styles.fabRow, { bottom: 24 + (pad ?? 0) }]}>
        <Pressable style={styles.fabPrimary} onPress={() => setShowSafety(true)}>
          <Text style={styles.fabText}>화재 대피 안내</Text>
        </Pressable>
        <Pressable style={styles.fabSecondary} onPress={() => setShowAppGuide(true)}>
          <Text style={styles.fabText}>앱 사용 안내</Text>
        </Pressable>
      </View>

      {/* 안전 안내 모달 */}
      <SafetyOverlay
        visible={showSafety}
        onClose={() => setShowSafety(false)}
        manualSrc={FIRE_ESCAPE_IMG}
        extinguisherSrc={EXTINGUISHER_IMG}
      />

      {/* 앱 사용 안내 (단일 이미지) */}
      <ImageOverlay
        visible={showAppGuide}
        onClose={() => setShowAppGuide(false)}
        src={APP_GUIDE_SRC}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#fff' },

  // 상단 미니 배너
  banner: {
    position: 'absolute',
    top: 16,
    left: 16,
    right: 16,
    backgroundColor: '#b91c1c',
    padding: 12,
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  bannerTxt: { color: 'white', fontWeight: '700', flex: 1 },
  bannerBtn: { paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#111827', borderRadius: 8 },
  bannerBtnTxt: { color: 'white', fontWeight: '700' },
  bannerClose: { paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#374151', borderRadius: 8 },

  // 하단 FAB
  fabRow: {
    position: 'absolute',
    right: 16,
    flexDirection: 'row',
    gap: 8,
  },
  fabPrimary: {
    backgroundColor: '#2563eb',
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingVertical: 12,
    elevation: 3,
  },
  fabSecondary: {
    backgroundColor: '#10b981',
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingVertical: 12,
    elevation: 3,
  },
  fabText: { color: '#fff', fontWeight: '700' },
});