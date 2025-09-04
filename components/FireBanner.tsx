// components/FireBanner.tsx
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const BANNER_HEIGHT = 44;  // 배너 고정 높이

export default function FireBanner({
  visible,
  text,
  onPressGuide,
  onClose,
}: {
  visible: boolean;
  text: string;
  onPressGuide?: () => void;
  onClose?: () => void;
}) {
  const insets = useSafeAreaInsets();
  if (!visible) return null;

  return (
    <View style={[styles.wrap, { top: insets.top + 8 }]}>
      <Text style={styles.txt} numberOfLines={1}>{text}</Text>
      <Pressable style={styles.btn} onPress={onPressGuide}>
        <Text style={styles.btnTxt}>안내 보기</Text>
      </Pressable>
      <Pressable style={[styles.btn, styles.close]} onPress={onClose}>
        <Text style={styles.btnTxt}>닫기</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 12,
    right: 12,
    height: BANNER_HEIGHT,
    backgroundColor: '#b91c1c',
    borderRadius: 12,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    zIndex: 100,
    elevation: 10,
  },
  txt: { color: '#fff', fontWeight: '700', flex: 1 },
  btn: { paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#111827', borderRadius: 10 },
  close: { backgroundColor: '#374151' },
  btnTxt: { color: '#fff', fontWeight: '700' },
});