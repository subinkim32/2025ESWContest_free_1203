// app/(tabs)/_layout.tsx
import { Ionicons } from '@expo/vector-icons';
import { Tabs, useRouter } from 'expo-router';
import React, { useEffect, useRef } from 'react';
import { ensureWS, WS_URL, wsOnMessage } from '../../config/ws';
import * as Notifications from 'expo-notifications';
import { getPushTokenAsync } from '../src/_appInit';

export default function TabLayout() {
  const router = useRouter();
  const lastFloorRef = useRef<string | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;

    (async () => {
      const token = await getPushTokenAsync();
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        console.log('[WS] opened');
        if (token) {
          ws!.send(JSON.stringify({ kind: 'register_push_token', token }));
        }
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(String(e.data));

          if (msg.kind === 'fire_detected') {
            Notifications.scheduleNotificationAsync({
              content: {
                title: '🔥 화재 감지',
                body: `신뢰도 ${msg.conf}`,
                data: msg,
              },
              trigger: null,
            });
          }
        } catch {}
      };

      ws.onerror = (err) => console.warn('[WS] error', err);
      ws.onclose = () => console.log('[WS] closed');
    })();

    return () => {
      ws?.close();
    };
  }, []);

  useEffect(() => {
    ensureWS();
    console.log('[WS root] ensure connect:', WS_URL);

    const off = wsOnMessage((msg) => {
      try {
        const floor = String(msg?.floor || '').toUpperCase();
        const map: Record<string, string> = {
          B1: '/(tabs)/b1',
          '1F': '/(tabs)/f1',
          '4F': '/(tabs)/f4',
          B2: '/(tabs)/b2',
        };
        const path = map[floor];
        if (path && lastFloorRef.current !== floor) {
          lastFloorRef.current = floor;
          router.push(path);
        }
      } catch {}
    });

    return off;
  }, [router]);

  return (
    <Tabs screenOptions={{ headerShown: false }}>
      <Tabs.Screen
        name="b2"
        options={{
          title: 'B2',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="grid-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="b1"
        options={{
          title: 'B1',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="layers-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="f1"
        options={{
          title: 'F1',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="navigate-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="f4"
        options={{
          title: 'F4',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="navigate-circle-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="scanBle"
        options={{
          title: 'scanBle',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="bluetooth-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen name="index" options={{ href: null }} />
    </Tabs>
  );
}