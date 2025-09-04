import React from 'react';
import { Image, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

type Props = {
  visible: boolean;
  onClose: () => void;
  src: number | string;
};

export default function ImageOverlay({ visible, onClose, src }: Props) {
  const source = typeof src === 'number' ? src : { uri: src };
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Image
            source={source}
            resizeMode="contain"
            style={{ width: '100%', height: 320 }}
          />
          <Pressable onPress={onClose} style={styles.closeBtn}>
            <Text style={styles.closeText}>닫기</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  card: {
    width: '100%',
    maxWidth: 520,
    borderRadius: 12,
    backgroundColor: '#111827',
    padding: 12,
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOpacity: 0.3, shadowRadius: 10, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 6 },
      default: {},
    }),
  },
  closeBtn: {
    alignSelf: 'flex-end',
    marginTop: 12,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#374151',
  },
  closeText: { color: '#fff', fontWeight: '700' },
});