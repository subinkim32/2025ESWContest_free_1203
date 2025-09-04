import React from 'react';
import {
    Image,
    Modal,
    Pressable,
    ScrollView,
    StyleSheet,
    Text,
    View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

type Props = {
  visible: boolean;
  onClose: () => void;
  evacuateImg: any;
  extinguisherImg: any;
  rotateEvac?: '0deg'|'90deg'|'180deg'|'270deg';
  rotateExt?:  '0deg'|'90deg'|'180deg'|'270deg';
};

export default function SafetyGuideModal({
  visible, onClose, evacuateImg, extinguisherImg,
  rotateEvac = '0deg', rotateExt = '0deg',
}: Props) {
  const insets = useSafeAreaInsets();
  const [tab, setTab] = React.useState<'evac' | 'ext'>('evac');

  const evacMeta = Image.resolveAssetSource(evacuateImg);
  const extMeta  = Image.resolveAssetSource(extinguisherImg);
  const ratio = tab === 'evac'
    ? evacMeta.width / evacMeta.height
    : extMeta.width / extMeta.height;

  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop} />

      <View style={[
        styles.sheet,
        { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 8 },
      ]}>
        {/* 헤더 */}
        <View style={styles.header}>
          <View style={styles.segment}>
            <Pressable
              onPress={() => setTab('evac')}
              style={[styles.segBtn, tab === 'evac' && styles.segBtnActive]}
            >
              <Text style={[styles.segTxt, tab === 'evac' && styles.segTxtActive]}>
                화재 시 대피 방법
              </Text>
            </Pressable>
            <Pressable
              onPress={() => setTab('ext')}
              style={[styles.segBtn, tab === 'ext' && styles.segBtnActive]}
            >
              <Text style={[styles.segTxt, tab === 'ext' && styles.segTxtActive]}>
                소화기 사용 방법
              </Text>
            </Pressable>
          </View>

          <Pressable onPress={onClose} style={styles.close}>
            <Text style={{ fontSize: 18 }}>✕</Text>
          </Pressable>
        </View>

        {/* 컨텐츠(핀치줌: iOS 기본 지원) */}
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={styles.zoom}
          maximumZoomScale={3}
          minimumZoomScale={1}
          centerContent
        >
          <Image
            source={tab === 'evac' ? evacuateImg : extinguisherImg}
            resizeMode="contain"
            style={[
              { width: '100%', aspectRatio: ratio },
              tab === 'evac' ? { transform: [{ rotate: rotateEvac }] }
                             : { transform: [{ rotate: rotateExt  }] },
            ]}
          />
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  sheet: {
    position: 'absolute',
    left: 12, right: 12, top: 12, bottom: 12,
    backgroundColor: '#fff',
    borderRadius: 14,
    overflow: 'hidden',
  },
  header: {
    paddingHorizontal: 12, paddingVertical: 8,
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5',
  },
  segment: {
    flexDirection: 'row', backgroundColor: '#f1f1f1',
    borderRadius: 8, overflow: 'hidden',
  },
  segBtn: { paddingHorizontal: 10, paddingVertical: 6 },
  segBtnActive: { backgroundColor: '#111' },
  segTxt: { fontSize: 12, color: '#333' },
  segTxtActive: { color: '#fff', fontWeight: '600' },
  close: { padding: 8, marginLeft: 8 },
  zoom: { padding: 12 },
});
