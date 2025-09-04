import React from 'react';
import {
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Image } from 'expo-image';

type Src = string | number;

function toSource(src?: Src) {
  if (!src) return undefined;
  return typeof src === 'string' ? { uri: src } : src;
}

interface Props {
  visible: boolean;
  onClose: () => void;
  manualSrc?: Src;       // 화재 대피 매뉴얼
  extinguisherSrc?: Src; // 소화기 사용법
  title?: string;
}

export default function SafetyOverlay({
  visible,
  onClose,
  manualSrc,
  extinguisherSrc,
  title = '안전 안내',
}: Props) {
  // 이미지 로딩 에러 확인용
  const onErr = (label: string) => (e: any) =>
    console.warn(`[SafetyOverlay] ${label} load error`, e?.nativeEvent ?? e);

  return (
    <Modal visible={visible} animationType="fade" transparent>
      {/* 어두운 배경 */}
      <Pressable style={styles.backdrop} onPress={onClose} />

      <View style={styles.sheet}>
        <View style={styles.header}>
          <Text style={styles.title}>{title}</Text>
          <Pressable onPress={onClose} hitSlop={12} style={styles.closeBtn}>
            <Text style={styles.closeTxt}>닫기</Text>
          </Pressable>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          {manualSrc ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>화재 시 대피 방법</Text>
              <Image
                source={toSource(manualSrc)}
                style={styles.image}
                contentFit="contain"
                onError={onErr('manual')}
                // 캐시 정책(선택)
                cachePolicy="memory-disk"
                // iOS http 차단 시 fallback 문구
              />
            </View>
          ) : null}

          {extinguisherSrc ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>소화기 사용 방법</Text>
              <Image
                source={toSource(extinguisherSrc)}
                style={styles.image}
                contentFit="contain"
                onError={onErr('extinguisher')}
                cachePolicy="memory-disk"
              />
            </View>
          ) : null}

          {!manualSrc && !extinguisherSrc ? (
            <Text style={{ color: '#666' }}>
              표시할 안내 이미지가 없습니다.
            </Text>
          ) : null}
        </ScrollView>
      </View>
    </Modal>
  );
}

const SHEET_MAX_W = 900;

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject as any,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  sheet: {
    position: 'absolute',
    left: 12,
    right: 12,
    top: Platform.select({ web: 24, default: 48 }),
    bottom: Platform.select({ web: 24, default: 48 }),
    alignSelf: 'center',
    maxWidth: SHEET_MAX_W,
    backgroundColor: '#fff',
    borderRadius: 16,
    overflow: 'hidden',
    ...Platform.select({
      web: { boxShadow: '0 10px 30px rgba(0,0,0,0.25)' } as any,
      default: { elevation: 10 },
    }),
  },
  header: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e5e7eb',
    backgroundColor: '#f8fafc',
    flexDirection: 'row',
    alignItems: 'center',
  },
  title: { fontSize: 18, fontWeight: '700', flex: 1 },
  closeBtn: { paddingHorizontal: 8, paddingVertical: 6 },
  closeTxt: { color: '#2563eb', fontWeight: '600' },
  content: {
    padding: 16,
    gap: 16,
    alignItems: 'stretch',
  },
  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#e5e7eb',
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#fff',
  },
  cardTitle: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontWeight: '700',
    backgroundColor: '#f1f5f9',
  },
  image: {
    width: '100%',
    // 화면에 꽉 차되 스크롤 가능하도록 높이만 적절히
    height: 520,
    backgroundColor: '#00000008',
  },
});
