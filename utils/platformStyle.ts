// utils/platformStyle.ts
import { Platform, ViewStyle } from 'react-native';

export const shadowStyle: ViewStyle | any = Platform.OS === 'web'
  ? { boxShadow: '0 8px 20px rgba(0,0,0,0.12)' }
  : {
      shadowColor: '#000',
      shadowOpacity: 0.15,
      shadowRadius: 10,
      shadowOffset: { width: 0, height: 6 },
    };

export const peNoneStyle: any = Platform.OS === 'web' ? { pointerEvents: 'none' } : undefined;
export const peNoneProp = Platform.OS !== 'web' ? { pointerEvents: 'none' as const } : {};
