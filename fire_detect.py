# fire_detect.py
import glob, os, asyncio, base64, json
from pathlib import Path
from ultralytics import YOLO
import cv2
import websockets

# ====== WS 설정 ======
WS_CANDIDATES = [
    "ws://172.20.6.45:8000",    # IPv4 주소 수정
]
# ====== 노트북 환경에 맞추어 설정 ======
MODEL_PATH = r"C:\Users\kimsu\Downloads\tamhwadan\tamhwadan\best_retrained.pt"
IMAGE_GLOB = r"C:\Users\kimsu\Downloads\tamhwadan\tamhwadan\test_images\*.jpg"
CLASS_NAMES = ['fire', 'smoke']

# ====== 모델 로드 ======
model = YOLO(MODEL_PATH)

def encode_jpg_b64(img_bgr) -> str:
    ok, buf = cv2.imencode(".jpg", img_bgr)
    if not ok:
        return ""
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"

async def send_ws_fire_any(conf: float, floor="B1", image_bgr=None):
    """여러 후보 WS 주소 중 하나로 전송 시도"""
    payload = {
        "kind": "fire_alert",
        "floor": floor,
        "confidence": round(float(conf), 3),
    }
    if image_bgr is not None:
        payload["image"] = encode_jpg_b64(image_bgr)

    text = json.dumps(payload, ensure_ascii=False)

    last_error = None
    for url in WS_CANDIDATES:
        try:
            async with websockets.connect(url, open_timeout=5, ping_interval=None) as ws:
                await ws.send(text)
                print(f"📤 fire_alert sent to {url}")
                return True
        except Exception as e:
            print(f"WS send failed to {url}: {e}")
            last_error = e
    print("WS send failed to all candidates.", last_error)
    return False

def safe_show_or_save(title: str, img, image_path: str):
    """GUI 없으면 저장으로 fallback"""

    out_dir = Path(__file__).with_name("fire_out")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / (Path(image_path).stem + "_result.jpg")
    cv2.imwrite(str(out_file), img)
    print(f"(GUI 없음) 결과 이미지를 저장했습니다: {out_file}")

async def broadcast_fire_at_node(floor: str, node_xy=(-18,-19), conf=0.0, image_bgr=None):
    """fire_alert + hazard(표시용) + delete_node(경로차단) 세트 전송"""
    def b64(img):
        ok, buf = cv2.imencode(".jpg", img)
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii") if ok else None

    payloads = [
        {"kind": "fire_alert", "floor": floor, "confidence": round(float(conf), 3)},
        {"kind": "hazard", "floor": floor, "node": list(node_xy), "active": True},   # 앱이 아이콘 표시
        {"kind": "delete_node", "floor": floor, "node": list(node_xy)},             # 경로 엔진이 노드 제거
    ]
    if image_bgr is not None:
        img64 = b64(image_bgr)
        if img64:
            payloads[0]["image"] = img64

    text_list = [json.dumps(p, ensure_ascii=False) for p in payloads]

    for url in WS_CANDIDATES:
        try:
            async with websockets.connect(url, open_timeout=5, ping_interval=None) as ws:
                for t in text_list:
                    await ws.send(t)
                print(f"📤 fire@{node_xy} broadcast to {url}")
                return True
        except Exception as e:
            print(f"WS send failed to {url}: {e}")
    return False
    
def main():
    image_paths = glob.glob(IMAGE_GLOB)
    if not image_paths:
        print("테스트 이미지가 없습니다:", IMAGE_GLOB)
        return

    for image_path in image_paths:
        image = cv2.imread(image_path)
        if image is None:
            print("skip unreadable:", image_path)
            continue

        results = model(image)[0]
        annotated = results.plot()

        # fire 판정
        fire_detected = False
        high_conf = 0.0
        for box in results.boxes:
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            label = CLASS_NAMES[cls_id] if 0 <= cls_id < len(CLASS_NAMES) else str(cls_id)
            if label.lower() == 'fire' and conf > 0.5:
                fire_detected = True
                high_conf = max(high_conf, conf)

        if fire_detected:
            print(f"[🔥] {os.path.basename(image_path)}: 화재 감지 (conf={high_conf:.2f})")
            # 앱으로 화재 알림 전송 (Base64 이미지 포함)
            asyncio.run(broadcast_fire_at_node(floor="B1", node_xy=(-18,-19), conf=high_conf, image_bgr=annotated))

        # 결과 표시
        safe_show_or_save("Result", annotated, image_path)

    try:
        cv2.destroyAllWindows()
    except Exception:
        pass

if __name__ == "__main__":
    main()
