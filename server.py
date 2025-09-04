# server.py
import asyncio, json, time
from typing import List, Dict, Any, Tuple
from collections import deque
import websockets
import datetime as dt

# final.py에서 공용 로직/데이터 사용
from final import (
    beacon_coords,
    trilaterate_from_top3,
    compute_best_path,
    classify_area,
    FLOOR_TO_GRAPH_MAP, graph_filename, original_filename,
    load_graph, save_graph, ensure_files,
    parse_node, remove_node, ORIGINAL_GRAPHS,
)

# ====== 서버 설정 ======
HOST = "172.20.6.45"      # IPv4 주소 수정
PORT = 8000

# ====== 트리거/필터 설정 ======
COUNT_TRIGGER   = 10      # Top3 각 비콘의 유효 샘플(>-99) 최소 개수
MAX_WINDOW_AGE  = 10.0    # 오래된 배치 버리는 최대 보관 시간(초)
RSSI_MIN_VALID  = -99     # 유효 RSSI 하한(이하 값은 제외)

# ====== 화재 발생 노드 영구 삭제 ======
# fire_alert 직후 이 시간 내 delete_node면 화재 유발 삭제로 간주(초)
FIRE_DELETE_WINDOW = 5.0

# 최근 층별 화재 알림 시각
RECENT_FIRE_TS: Dict[str, float] = {"B2": 0.0, "B1": 0.0, "1F": 0.0, "4F": 0.0}

# 복구 금지 노드(층별)
FIRE_BLOCKED_NODES: Dict[str, set] = {"B2": set(), "B1": set(), "1F": set(), "4F": set()}


clients = set()

# 🔥 화재 알림 옵션
DROP_FIRE_IMAGE = True    # fire_alert payload에서 base64 이미지 제거
ADD_TIMESTAMP   = True    # fire_alert에 ISO 시간스탬프(ts) 추가
HAZARDS = {"B2": set(), "B1": set(), "1F": set(), "4F": set()}

# ====== 유틸 ======
def compress_batch_for_log(batch: Dict[str, Any]) -> list:
    out = []
    for r in batch.get("readings", []):
        val = r.get("filtered", r.get("rssi"))
        try:
            v = None if val is None else round(float(val), 1)
        except Exception:
            v = None
        out.append((r.get("id"), v))
    return out

def _is_valid(v):
    try:
        return v is not None and float(v) > RSSI_MIN_VALID
    except Exception:
        return False

def prune_old(window: deque, max_age: float = MAX_WINDOW_AGE):
    """너무 오래된 배치는 버려서 메모리/추정 왜곡 방지"""
    now = time.time()
    while window and (now - window[0]["ts"] > max_age):
        window.popleft()

def push_batch(window: deque, lst: list):
    readings = []
    for r in lst:
        readings.append({
            "id": r.get("id"),
            "filtered": r.get("filtered"),
            "rssi": r.get("rssi"),
        })
    window.append({"ts": time.time(), "readings": readings})

# ====== 집계/Top3 ======
def aggregate_window(window: deque) -> Dict[int, Dict[str, float]]:
    """
    윈도우에 쌓인 배치들에서 비콘별 평균/카운트 계산.
    - avg_filtered: filtered 평균 (>-99만 집계)
    - avg_rssi: raw 평균 (>-99만 집계)
    - count: 유효 샘플 수(둘 중 큰 값)
    """
    acc: Dict[int, Dict[str, float]] = {}
    for b in window:
        for r in b.get("readings", []):
            bid = r.get("id")
            if bid not in beacon_coords:
                continue
            fil = r.get("filtered")
            raw = r.get("rssi")

            # 이상치 드랍(하한 -99), useBle.ts 버그 방지
            if not _is_valid(fil): fil = None
            if not _is_valid(raw): raw = None

            if bid not in acc:
                acc[bid] = {"sum_fil": 0.0, "cnt_fil": 0, "sum_raw": 0.0, "cnt_raw": 0}
            if fil is not None:
                acc[bid]["sum_fil"] += float(fil); acc[bid]["cnt_fil"] += 1
            if raw is not None:
                acc[bid]["sum_raw"] += float(raw); acc[bid]["cnt_raw"] += 1

    out: Dict[int, Dict[str, float]] = {}
    for bid, d in acc.items():
        avg_fil = d["sum_fil"]/d["cnt_fil"] if d["cnt_fil"]>0 else None
        avg_raw = d["sum_raw"]/d["cnt_raw"] if d["cnt_raw"]>0 else None
        cnt = max(d["cnt_fil"], d["cnt_raw"])
        out[bid] = {"avg_filtered": avg_fil, "avg_rssi": avg_raw, "count": cnt}
    return out

def pick_top3_ready_by_count(window: deque, min_count: int = COUNT_TRIGGER):
    """
    시간 무관, 유효 샘플 수로 트리거:
    - 집계 후 Top3 후보를 고르고,
    - 각 후보의 'count'가 min_count 이상이면 Top3 반환, 아니면 None.
    """
    stats = aggregate_window(window)

    def score(item):
        _, d = item
        v = d.get("avg_filtered")
        if v is None:
            v = d.get("avg_rssi", -9999.0)
        return float(v)

    candidates = []
    for bid, d in stats.items():
        m = d["avg_filtered"] if d["avg_filtered"] is not None else d["avg_rssi"]
        if m is None:
            continue
        try:
            if float(m) <= RSSI_MIN_VALID:
                continue
        except Exception:
            continue
        candidates.append((bid, d))

    candidates.sort(key=score, reverse=True)
    top = candidates[:3]
    if len(top) < 3:
        return None

    # 각 후보의 유효 샘플 수 확인
    for _, d in top:
        if int(d.get("count", 0)) < min_count:
            return None

    # Top3 payload 변환
    top3 = []
    for bid, d in top:
        top3.append({
            "id": bid,
            "filtered": None if d["avg_filtered"] is None else float(d["avg_filtered"]),
            "rssi": None if d["avg_rssi"] is None else float(d["avg_rssi"]),
            "distance": None,
            "count": int(d["count"]),
        })
    return top3

# ====== 그래프 조작 ======
def _restore_node_in_graph(floor: str, node) -> bool:
    """원본 그래프에서 해당 node의 이웃을 가져와 현재 그래프에 복구. 단, 화재 유발 삭제 노드는 복구 불가."""
    if floor not in FLOOR_TO_GRAPH_MAP: return False
    num = FLOOR_TO_GRAPH_MAP[floor]
    if not ensure_files(num): return False

    # 화재 유발 삭제 노드면 복구 금지
    if floor in FIRE_BLOCKED_NODES and node in FIRE_BLOCKED_NODES[floor]:
        print(f"[Graph] restore_node 차단: {node} (floor={floor}) is FIRE-BLOCKED")
        return False
    
    gfile = graph_filename(num)
    ofile = original_filename(num)

    graph = load_graph(gfile)
    orig = ORIGINAL_GRAPHS.get(ofile, {})

    if node not in orig:
        return False

    # 노드 및 양방향 간선 복구(이웃이 현재 그래프에 존재하는 경우에 한해 연결)
    neighbors = [n for n in orig[node] if n in graph or n in orig]
    if node not in graph:
        graph[node] = []

    for nb in neighbors:
        if nb not in graph:
            continue
        if nb not in graph[node]:
            graph[node].append(nb)
        if node not in graph[nb]:
            graph[nb].append(node)

    save_graph(graph, gfile)
    return True

# ====== 즉시 계산/브로드캐스트 ======
async def _emit_with_top3(top3, floor: str, window: deque, tag: str = ""):
    try:
        x, y, method = trilaterate_from_top3(top3, use_filtered=True)
    except Exception as e:
        print("[Tri] 실패:", e)
        return

    try:
        area = classify_area((x, y), floor, strict=False)
    except Exception:
        area = None

    try:
        start_node, best_path = compute_best_path(floor, x, y)
    except Exception as e:
        print("[Path] 계산 실패:", e)
        return

    window_log = [compress_batch_for_log(b) for b in list(window)]
    top3_log = [(t["id"], round(t.get("filtered", t.get("rssi", -999)), 2), t["count"]) for t in top3]
    print(f"[Tri{tag}] floor={floor}, method={method}, TAG=({x:.2f}, {y:.2f}) | top3={top3_log}")
    print(f"[RSSI window] {window_log}")
    print(f"[Area] floor={floor}, area={area}")
    print(f"[Path] start={start_node}, path_len={len(best_path)}")

    payload = {
        "floor": floor,
        "snapped_list": [list(start_node)],
        "best_path": [list(pt) for pt in best_path],
        "note": "live_update",
        "method": method,
        "area": area,
        "debug": { "top3": top3, "tag_xy": [x, y], "recent_batches": list(window) },
    }
    await asyncio.gather(
        *[c.send(json.dumps(payload, ensure_ascii=False)) for c in list(clients)]
    )

# ====== 메인 핸들러 ======
async def handle(ws):
    clients.add(ws)
    window = deque()            # 길이 제한 제거 (count 트리거)
    last_floor = "B2"

    try:
        async for text in ws:
            # 🔥 화재 알림: 즉시 브로드캐스트
            try:
                maybe_json = json.loads(text)
                if (maybe_json.get("kind") or "") == "fire_alert":
                    floor = maybe_json.get("floor")
                    conf = maybe_json.get("confidence")
                    print(f"🔥 fire_alert received: floor={floor}, conf={conf}")

                    # 층별 최근 화재 시각 기록
                    if isinstance(floor, str) and floor in RECENT_FIRE_TS:
                        RECENT_FIRE_TS[floor] = time.time()
                    if DROP_FIRE_IMAGE:
                        maybe_json.pop("image", None)
                    if ADD_TIMESTAMP:
                        maybe_json["ts"] = dt.datetime.now().isoformat(timespec="seconds")

                    fire_text = json.dumps(maybe_json, ensure_ascii=False)
                    if clients:
                        await asyncio.gather(
                            *[c.send(fire_text) for c in list(clients)],
                            return_exceptions=True
                        )
                    continue
            except Exception:
                pass

            # ====== BLE / 그래프 조작 처리 ======
            try:
                msg = json.loads(text)
            except Exception:
                continue

            kind = (msg.get("kind") or "").strip()

            # ====== BLE 수신 ======
            if kind == "rssi_batch":
                last_floor = msg.get("floor", last_floor)
                readings = msg.get("readings", [])
                window.append({"ts": time.time(), "readings": readings})

            elif kind == "ble_readings":
                last_floor = msg.get("floor", last_floor)
                lst = msg.get("list", [])
                push_batch(window, lst)

            elif kind == "floor_detected":
                f = msg.get("floor")
                if isinstance(f, str) and f in ("B2","B1","1F","4F"):
                    last_floor = f

            # ====== 그래프 조작 ======
            elif kind in ("graph_delete", "delete_node", "remove_node"):
                floor = msg.get("floor", last_floor)
                node_payload = msg.get("node") or msg.get("id")
                try:
                    node = parse_node(node_payload)
                except Exception:
                    print("[Graph] delete 실패: node 파싱 오류:", node_payload)
                    continue
                
                now_ts = time.time()
                fire_related = False
                last_fire_ts = RECENT_FIRE_TS.get(floor, 0.0)
                if now_ts - last_fire_ts <= FIRE_DELETE_WINDOW:
                    fire_related = True

                num = FLOOR_TO_GRAPH_MAP.get(floor)
                if num is None or not ensure_files(num):
                    print("[Graph] delete 실패: ensure_files")
                    continue

                gfile = graph_filename(num)
                graph = load_graph(gfile)
                remove_node(graph, node)
                save_graph(graph, gfile)
                print(f"[Graph] deleted {node} on {floor}")

                # 화재 유발 노드면 복구 금지 목록에 등록
                if fire_related:
                    FIRE_BLOCKED_NODES.setdefault(floor, set()).add(node)

                await ws.send(json.dumps({"kind":"graph_ack","op":"delete","floor":floor,"node":list(node),"fire_related":fire_related}))
                # 그래프 변경 즉시 재계산
                top3 = pick_top3_ready_by_count(window, COUNT_TRIGGER)
                if top3:
                    await _emit_with_top3(top3, floor, window, tag="*")
                continue

            elif kind in ("graph_restore", "restore_graph"):
                floor = msg.get("floor", last_floor)
                num = FLOOR_TO_GRAPH_MAP.get(floor)
                if num is None or not ensure_files(num):
                    print("[Graph] restore 실패: ensure_files")
                    continue

                ofile = original_filename(num)
                gfile = graph_filename(num)
                orig = ORIGINAL_GRAPHS.get(ofile, {}).copy()  # dict copy

                # FIRE_BLOCKED_NODES에 등록된 노드는 원상복구하지 않음
                blocked = FIRE_BLOCKED_NODES.get(floor, set())
                if blocked:
                    for bn in list(blocked):
                        if bn in orig:
                            # 노드 키 제거
                            orig.pop(bn, None)
                    # 양방향 간선에서 차단 노드 제거
                    for k, neigh in orig.items():
                        if isinstance(neigh, list):
                            orig[k] = [x for x in neigh if x not in blocked]

                save_graph(orig, gfile)  # 원본(차단 제외)으로 덮기
                print(f"[Graph] restored ALL on {floor} (blocked_excluded={len(blocked)})")

                await ws.send(json.dumps({"kind":"graph_ack","op":"restore_all","floor":floor,"blocked_excluded":len(blocked)}))
                top3 = pick_top3_ready_by_count(window, COUNT_TRIGGER)
                if top3:
                    await _emit_with_top3(top3, floor, window, tag="*")
                continue

            elif kind in ("graph_restore_node", "restore_node"):
                floor = msg.get("floor", last_floor)
                node_payload = msg.get("node") or msg.get("id")
                try:
                    node = parse_node(node_payload)
                except Exception:
                    print("[Graph] restore_node 실패: node 파싱 오류:", node_payload)
                    continue

                ok = _restore_node_in_graph(floor, node)
                print(f"[Graph] restore_node {node} on {floor} -> {ok}")
                await ws.send(json.dumps({"kind":"graph_ack","op":"restore_node","floor":floor,"node":list(node),"ok":ok}))
                top3 = pick_top3_ready_by_count(window, COUNT_TRIGGER)
                if top3:
                    await _emit_with_top3(top3, floor, window, tag="*")
                continue

            elif kind == "hazard":
                floor = msg.get("floor", last_floor)
                node_payload = msg.get("node")
                active = bool(msg.get("active", True))

                try:
                    node = parse_node(node_payload)  # (x,y) 튜플로
                except Exception:
                    print("[Hazard] node 파싱 오류:", node_payload)
                    continue

                s = HAZARDS.setdefault(floor, set())
                if active:
                    s.add(node)
                else:
                    s.discard(node)

                # 현재 상태를 모두에게 방송
                state = {
                    "kind": "hazard_state",
                    "floor": floor,
                    "hazard_nodes": [list(n) for n in s],
                }
                await asyncio.gather(
                    *[c.send(json.dumps(state, ensure_ascii=False)) for c in list(clients)],
                    return_exceptions=True
                )
                continue

            else:
                continue

            # ====== "개수 트리거" 검사 ======
            prune_old(window, MAX_WINDOW_AGE)
            top3 = pick_top3_ready_by_count(window, COUNT_TRIGGER)
            if top3 is not None:
                await _emit_with_top3(top3, last_floor, window)
                # 다음 사이클 시작을 위해 윈도우 초기화
                window.clear()

    finally:
        clients.discard(ws)

# ====== 메인 ======
async def main():
    print(f"WebSocket server listening on ws://{HOST}:{PORT}")
    async with websockets.serve(handle, HOST, PORT, ping_interval=20, ping_timeout=20):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())