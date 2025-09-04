// app/(tabs)/index.tsx
import { useEffect } from "react";
import { useRouter } from "expo-router";

export default function IndexRedirect() {
  const router = useRouter();

  useEffect(() => {
    // 앱 실행 시 바로 scanBle 화면으로 교체
    router.replace("/(tabs)/scanBle");
  }, [router]);

  // 화면에 아무것도 안 보여주고 바로 넘어가게
  return null;
}
