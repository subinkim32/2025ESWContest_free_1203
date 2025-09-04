// app/_appInit.ts (또는 루트 레이아웃에 삽입)
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';

export async function getPushTokenAsync() {
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== 'granted') return null;

  // Expo Go에서도 동작하는 토큰
  const projectId = Constants.expoConfig?.extra?.eas?.projectId
                 ?? Constants.easConfig?.projectId;
  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  return token; // "ExponentPushToken[...]" 형태
}
