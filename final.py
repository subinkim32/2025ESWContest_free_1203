# final.py

import os, json, math
import numpy as np
import re
from statistics import mean
from collections import deque
from scipy.optimize import least_squares

# ===== AP 클래스 및 삼변측량 =====
class AP:
    def __init__(self, x, y, distance):
        self.x = x
        self.y = y
        self.distance = distance

class Trilateration:
    def __init__(self, AP1, AP2, AP3):
        self.AP1 = AP1
        self.AP2 = AP2
        self.AP3 = AP3
        self.aps = [AP1, AP2, AP3]

    def _can_circles_intersect(self, p1, r1, p2, r2, label1, label2, debug):
        d = np.linalg.norm(np.array(p1) - np.array(p2))
        if d > r1 + r2:
            if debug:
                print(f"{label1}과 {label2}의 원이 겹치지 않음 (중심 거리: {d:.2f}, 반지름 합: {r1 + r2:.2f})")
            return False
        if d < abs(r1 - r2):
            if debug:
                print(f"{label1}과 {label2}의 원이 포함관계로 교차 불가 (중심 거리: {d:.2f}, 반지름 차: {abs(r1 - r2):.2f})")
            return False
        return True

    def is_valid(self, debug=False):
        p1, r1 = (self.AP1.x, self.AP1.y), self.AP1.distance
        p2, r2 = (self.AP2.x, self.AP2.y), self.AP2.distance
        p3, r3 = (self.AP3.x, self.AP3.y), self.AP3.distance

        ok12 = self._can_circles_intersect(p1, r1, p2, r2, "AP1", "AP2", debug)
        ok23 = self._can_circles_intersect(p2, r2, p3, r3, "AP2", "AP3", debug)
        ok13 = self._can_circles_intersect(p1, r1, p3, r3, "AP1", "AP3", debug)

        return ok12 and ok23 and ok13

    def calcUserLocation(self, method="direct", debug=False):
        if method == "direct":
            if not self.is_valid(debug=True):
                raise ValueError("세 거리로는 삼변측량이 불가능합니다.")
            A = 2 * (self.AP2.x - self.AP1.x)
            B = 2 * (self.AP2.y - self.AP1.y)
            C = self.AP1.distance**2 - self.AP2.distance**2 - self.AP1.x**2 + self.AP2.x**2 - self.AP1.y**2 + self.AP2.y**2
            D = 2 * (self.AP3.x - self.AP2.x)
            E = 2 * (self.AP3.y - self.AP2.y)
            F = self.AP2.distance**2 - self.AP3.distance**2 - self.AP2.x**2 + self.AP3.x**2 - self.AP2.y**2 + self.AP3.y**2
            user_x = ( (F * B) - (E * C) ) / ( (B * D) - (E * A))
            user_y = ( (F * A) - (D * C) ) / ( (A * E) - (D * B))
            return user_x, user_y

        elif method == "least_squares":
            def residuals(p):
                return [np.linalg.norm(np.array(p) - np.array([ap.x, ap.y])) - ap.distance for ap in self.aps]
            x0 = np.mean([ap.x for ap in self.aps])
            y0 = np.mean([ap.y for ap in self.aps])
            result = least_squares(residuals, x0=[x0, y0])
            return result.x[0], result.x[1]

        elif method == "auto":
            try:
                x, y = self.calcUserLocation(method="direct", debug=debug)
                return x, y, "direct"
            except ValueError:
                x, y = self.calcUserLocation(method="least_squares")
                return x, y, "least_squares"

        else:
            raise ValueError(f"알 수 없는 method: {method}")
        
# ====== server.py에서 실행할 top3 RSSI ======
def trilaterate_from_top3(top3_readings, *, use_filtered: bool = True):
    from math import isnan
    aps = []
    for r in top3_readings:
        bid = r["id"]
        if bid not in beacon_coords:
            raise ValueError(f"unknown beacon id: {bid}")
        bx, by = beacon_coords[bid]

        if r.get("distance") is not None:
            val = float(r["distance"])
            if not isnan(val):
                dist = val
            else:
                base = r.get("filtered") if use_filtered and (r.get("filtered") is not None) else r.get("rssi")
                dist = 10 ** ((-86 - float(base)) / 20.0)
        else:
            base = r.get("filtered") if use_filtered and (r.get("filtered") is not None) else r.get("rssi")
            dist = 10 ** ((-86 - float(base)) / 20.0)

        aps.append(AP(bx, by, dist))

    if len(aps) != 3:
        raise ValueError("need exactly 3 anchors")

    tril = Trilateration(*aps)
    x, y, method = tril.calcUserLocation(method="auto", debug=False)
    return x, y, method


# ====== 구역 판정 모듈 ======
class _Shape:
    def contains(self, pt): raise NotImplementedError
    def __call__(self, pt): return self.contains(pt)
    def __or__(self, other):
        return _Union([self, other])

class Rect(_Shape):
    __slots__ = ("xmin","ymin","xmax","ymax")
    def __init__(self, x1, y1, x2, y2):
        self.xmin, self.ymin = min(x1, x2), min(y1, y2)
        self.xmax, self.ymax = max(x1, x2), max(y1, y2)
    def contains(self, pt):
        x, y = pt
        return (self.xmin <= x <= self.xmax) and (self.ymin <= y <= self.ymax)

class _Union(_Shape):
    def __init__(self, shapes): self.shapes = shapes
    def contains(self, pt): return any(s.contains(pt) for s in self.shapes)
    def __or__(self, other):
        return _Union(self.shapes + ([other] if not isinstance(other, _Union) else other.shapes))

def rect(x1, y1, x2, y2) -> Rect:
    return Rect(x1, y1, x2, y2)

# ====== 구역 좌표 설정 ======
# B2
B2_01 = rect(-20, -33, -8, -5) | rect(-8, -33, -4, -19) | rect(-4, -33, 0, -29)
B2_02 = rect(-20, -5, -8, 11) | rect(-8, -5, -4, -1)
B2_03 = rect(-20, 11, -12, 15)
B2_04 = rect(-12, 11, -8, 15)
B2_05 = rect(-8, 11, -4, 15)
B2_06 = rect(-8, 11, -4, 7) | rect(-4, 7, 8, 15)
B2_07 = rect(-8, 3, 8, 7)
B2_08 = rect(-4, -1, -8, 3)
B2_09 = rect(-4, -1, 0, 3)
B2_10 = rect( 0, 3, 8, -1) | rect( 8, -1, 20, 15)
B2_11 = rect(-8, -5, -4, -19)
B2_12 = rect(-4, -5, 8, -1)
B2_13 = rect(-4, -5, 8, -9)
B2_14 = rect(-4, -13, 8, -9)
B2_15 = rect(-4, -13, 8, -17)
B2_16 = rect(-4, -21, 8, -17)
B2_17 = rect(-4, -21, 8, -25)
B2_18 = rect(-4, -25, 0, -29) | rect(0, -27, 8, -25)
B2_19 = rect(0, -27, 6, -33)
B2_20 = rect(6, -33, 8, -27)
B2_21 = rect(-20, -33, 8, -39)
B2_22 = rect(8, -39, 16, -33) | rect(12, -66, 8, -29) | rect(8, -29, 14, -23)
B2_23 = rect(14, -23, 22, -29) | rect(16, -29, 20, -33) | rect(16, -33, 22, -39)
B2_24 = rect(8, -17, 22, -23) | rect(22, -21, 26, -17)
B2_25 = rect( 8, -17, 22, -5) | rect(22, -13, 26, -17) | rect(26, -15, 38, -19)
B2_26 = rect(8, -1, 22, -5)
B2_27 = rect(20, 15, 24, -1)
B2_28 = rect(38, 15, 28, -1)
B2_29 = rect(22, -5, 38, -1)
B2_30 = rect(22, -5, 26, -9) | rect(26, -5, 38, -11)
B2_31 = rect(22, -13, 26, -9) | rect(26, -15, 38, -11)
B2_32 = rect(22, -21, 26, -25) | rect(26, -25, 38, -19)
B2_33 = rect(22, -29, 38, -25)
B2_34 = rect(20, -33, 22, -29) | rect(22, -29, 38, -39)
B2_35 = rect(12, -33, 16, -29)
B2_36 = rect(28, 15, 24, -1)

# B1
B1_01 = rect(-24, -17, -20, -21)
B1_02 = rect(-20, -21, -16, -17)
B1_03 = rect(-16, -17, -12, -21)
B1_04 = rect(-12, -21, -8, -17)
B1_05 = rect(-8, -17, 0, -21)
B1_06 = rect(-24, -17, -10, -13)
B1_07 = rect(-10, -17, 0, -17)
B1_08 = rect(-10, -13, -24, -9)
B1_09 = rect(-10, -13, 0, -9)
B1_10 = rect(-24, -9, -10, -5)
B1_11 = rect(-10, -5, 0, -9)
B1_12 = rect(-24, -1, -10, -5)
B1_13 = rect(-10, -5, -2, -1)
B1_14 = rect(-24, -1, -10, 3)
B1_15 = rect(-10, 3, -2, -1)
B1_16 = rect(-24, 7, -10, 3)
B1_17 = rect(-10, 3, -2, 7)
B1_18 = rect(-24, 7, -12, 14)
B1_19 = rect(-12, 14, -8, 7)
B1_20 = rect(-8, 7, -2, 14)
B1_21 = rect(0, 3, 4, -1) | rect(0, 3, 3, 5) | rect(-2, -1, 3, -4)
B1_22 = rect(4, -1, 8, 3) | rect(3, 5, 8, 3) | rect(8, 5, -2, 14) | rect(8, -1, 3, -4) | rect(8, -4, 0, -21)
B1_23 = rect(8, -4, 12, 11)
B1_24 = rect(12, 3, 20, 7)
B1_25 = rect(12, 3, 16, -4)
B1_26 = rect(16, -4, 20, 3) | rect(20, 1, 14, -1)
B1_27 = rect(12, 11, 20, 7)
B1_28 = rect(16, 11, 18, 15)
B1_29 = rect(16, 19, 18, 15)
B1_30 = rect(8, 19, 16, 11)
B1_31 = rect(20, 7, 24, 13)
B1_32 = rect(20, 7, 24, -4)
B1_33 = rect(24, 3, 28, 7)
B1_34 = rect(24, 13, 32, 7)

# F1
F1_01 = rect(16, 23, -10, 11)
F1_02 = rect(16, 11, -10, 7)
F1_03 = rect(-10, 7, 8, 3)
F1_04 = rect(-10, 3, 4, -18)
F1_05 = rect(8, 3, 4, -1)
F1_06 = rect(4, -1, 8, -18)
F1_07 = rect(12, 7, 8, -18)
F1_08 = rect(12, 7, 16, -18)
F1_09 = rect(42, 23, 16, -18)

# F4
F4_01 = rect(2, 17, -8, 9)
F4_02 = rect(2, 9, -8, 3)
F4_03 = rect(-4, 3, -8, -11)
F4_04 = rect(0, 3, -4, -1) | rect(-4, -1, 2, -11)
F4_05 = rect(4, 3, 0, -1)
F4_06 = rect(2, 17, 8, 3) | rect(4, 3, 8, -1) | rect(8, -1, 2, -11)
F4_07 = rect(12, 17, 8, -11)
F4_08 = rect(16, 17, 12, -11)
F4_09 = rect(32, 17, 16, -11)

# ====== 구역별 대표 노드 ======
NODES_BY_AREA = {
    "B1": {
        "B1_01": (-22,-19), "B1_02": (-18,-19), "B1_03": (-14,-19), "B1_04": (-10,-19),
        "B1_05": (-6,-19), "B1_06": (-18,-15), "B1_07": (-2,-15), "B1_08": (-18,-11),
        "B1_09": (-2,-11), "B1_10": (-18,-7), "B1_11": (-2,-7), "B1_12": (-18,-3),
        "B1_13": (-2,-3), "B1_14": (-18,1), "B1_15": (-2,1), "B1_16": (-18,5),
        "B1_17": (-2,5), "B1_18": (-14,9), "B1_19": (-10,9), "B1_20": (-6,9),
        "B1_21": (2,1), "B1_22": (6,1), "B1_23": (10,1), "B1_24": (18,5),
        "B1_25": (14,1), "B1_26": (18,1), "B1_27": (18,9), "B1_28": (18,13),
        "B1_29": (18,17), "B1_30": (14,13), "B1_31": (22,9), "B1_32": (22,5),
        "B1_33": (26,5), "B1_34": (26,9)
    },
    "B2": {
        "B2_01":(-2, -31), "B2_02":(-6, -3), "B2_03":(-14, 13), "B2_04":(-10, 13),
        "B2_05":(-6, 13), "B2_06":(-6, 9), "B2_07":(-6, 5), "B2_08":(-6, 1),
        "B2_09":(-2, 1), "B2_10":(18, 3), "B2_11":(-6, -7), "B2_12":(-2,-3),
        "B2_13":(-2, -7), "B2_14":(-2, -11), "B2_15":(-2, -15), "B2_16":(-2, -19),
        "B2_17":(-2, -23), "B2_18":(-2, -27), "B2_19":(2, -31), "B2_20":(6, -31),
        "B2_21":(2, -35), "B2_22":(10, -31), "B2_23":(18, -31), "B2_24":(24, -19),
        "B2_25":(24, -15), "B2_26":(18, 1), "B2_27":(22, 1), "B2_28":(30, 1),
        "B2_29":(24, -3), "B2_30":(24, -7), "B2_31":(24, -11), "B2_32":(24, -23),
        "B2_33":(24, -27), "B2_34":(22, -31), "B2_35":(14, -31), "B2_36":(26, 1)
    },
    "1F": {
        "F1_01": (4,13), "F1_02": (4,9), "F1_03": (4,5), "F1_04": (2,1),
        "F1_05": (6,1), "F1_06": (6,-3), "F1_07": (10,1), "F1_08": (14,1),
        "F1_09": (18,1)
    },
    "4F": {
        "F4_01": (-2,9), "F4_02": (-2,5), "F4_03": (-6,-3), "F4_04": (-2,1),
        "F4_05": (2,1), "F4_06": (6,1), "F4_07": (10,1), "F4_08": (14,1),
        "F4_09": (18,1)
    }
}

# ====== 층별 구역과 노드 매핑 ======
AREAS_BY_FLOOR = {
    "B1": {
        "B1_01": B1_01, "B1_02": B1_02, "B1_03": B1_03, "B1_04": B1_04, "B1_05": B1_05,
        "B1_06": B1_06, "B1_07": B1_07, "B1_08": B1_08, "B1_09": B1_09, "B1_10": B1_10,
        "B1_11": B1_11, "B1_12": B1_12, "B1_13": B1_13, "B1_14": B1_14, "B1_15": B1_15,
        "B1_16": B1_16, "B1_17": B1_17, "B1_18": B1_18, "B1_19": B1_19, "B1_20": B1_20,
        "B1_21": B1_21, "B1_22": B1_22, "B1_23": B1_23, "B1_24": B1_24, "B1_25": B1_25,
        "B1_26": B1_26, "B1_27": B1_27, "B1_28": B1_28, "B1_29": B1_29, "B1_30": B1_30,
        "B1_31": B1_31, "B1_32": B1_32, "B1_33": B1_33, "B1_34": B1_34,
    },
    "B2": {
        "B2_01": B2_01, "B2_02": B2_02, "B2_03": B2_03, "B2_04": B2_04, "B2_05": B2_05,
        "B2_06": B2_06, "B2_07": B2_07, "B2_08": B2_08, "B2_09": B2_09, "B2_10": B2_10,
        "B2_11": B2_11, "B2_12": B2_12, "B2_13": B2_13, "B2_14": B2_14, "B2_15": B2_15,
        "B2_16": B2_16, "B2_17": B2_17, "B2_18": B2_18, "B2_19": B2_19, "B2_20": B2_20,
        "B2_21": B2_21, "B2_22": B2_22, "B2_23": B2_23, "B2_24": B2_24, "B2_25": B2_25,
        "B2_26": B2_26, "B2_27": B2_27, "B2_28": B2_28, "B2_29": B2_29, "B2_30": B2_30,
        "B2_31": B2_31, "B2_32": B2_32, "B2_33": B2_33, "B2_34": B2_34, "B2_35": B2_35, "B2_36": B2_36,
    },
    "1F": {
        "F1_01": F1_01, "F1_02": F1_02, "F1_03": F1_03, "F1_04": F1_04, "F1_05": F1_05,
        "F1_06": F1_06, "F1_07": F1_07, "F1_08": F1_08, "F1_09": F1_09,
    },
    "4F": {
        "F4_01": F4_01, "F4_02": F4_02, "F4_03": F4_03, "F4_04": F4_04, "F4_05": F4_05,
        "F4_06": F4_06, "F4_07": F4_07, "F4_08": F4_08, "F4_09": F4_09,
    }
}

# ===== 비콘 좌표 설정 =====
beacon_coords = {
    1: (2, 1),
    2: (4, 3),
    3: (6, 1),
    4: (8, 3),
    5: (10, 1),
    6: (12, 3),
    7: (14, 1),
    8: (16, 3),
    9: (18, 1)
}

# ====== 층 → 그래프 번호 매핑 ======
FLOOR_TO_GRAPH_MAP = { "B2": 1, "B1": 2, "1F": 3, "4F": 4 }

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _p(*parts):
    return os.path.join(BASE_DIR, *parts)

# ====== 파일명 템플릿 ======
def original_filename(num): return f"original_graph{num}.json"
def graph_filename(num):    return f"graph_data{num}.json"
def targets_filename(num):  return f"targets{num}.json"

# ====== 저장/불러오기 함수 ======
def save_graph(graph, filename):
    path = _p(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({str(k): [str(vv) for vv in v] for k, v in graph.items()},
                  f, ensure_ascii=False, indent=2)

def load_graph(filename): # graph 불러오기
    path = _p(filename)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
        return {
            tuple(map(int, k.strip("()").split(","))):
            [tuple(map(int, vv.strip("()").split(","))) for vv in v]
            for k, v in raw.items()
        }

def save_targets(targets, filename):
    path = _p(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([str(t) for t in targets], f, ensure_ascii=False, indent=2)

def load_targets(filename): # target 불러오기
    path = _p(filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
        return [tuple(map(int, t.strip("()").split(","))) for t in raw]

def ensure_files(num): # 파일 초기화 함수
    orig_file = original_filename(num)
    graph_file = graph_filename(num)
    targets_file = targets_filename(num)

    # 원본 그래프 저장 (코드 내 사전 기준으로 덮어쓰기)
    if orig_file in ORIGINAL_GRAPHS:
        save_graph(ORIGINAL_GRAPHS[orig_file], orig_file)
    else:
        return False

    # 현재 그래프 없으면 원본에서 복사 생성
    if not os.path.exists(_p(graph_file)):
        save_graph(ORIGINAL_GRAPHS[orig_file], graph_file)

    # 도착지 파일 없으면 기본 도착지 저장
    if not os.path.exists(_p(targets_file)):
        targets = TARGETS_MAP.get(orig_file, [])
        save_targets(targets, targets_file)

    return True

def remove_node(graph, node_to_remove):
    if node_to_remove in graph:
        del graph[node_to_remove]
    for node, neighbors in graph.items():
        if node_to_remove in neighbors:
            neighbors.remove(node_to_remove)


# ====== BFS 최단경로 ======
def bfs_shortest_path(graph, start, target):
    distances = {node: math.inf for node in graph}
    parents = {node: None for node in graph}
    distances[start] = 0
    queue = deque([start])

    while queue:
        current = queue.popleft()
        if current == target:
            break
        for neighbor in graph.get(current, []):
            if distances[neighbor] == math.inf:
                distances[neighbor] = distances[current] + 1
                parents[neighbor] = current
                queue.append(neighbor)

    if distances[target] == math.inf:
        return math.inf, []

    path = []
    node = target
    while node is not None:
        path.append(node)
        node = parents[node]
    path.reverse()
    return distances[target], path

# 문자열 → 튜플
def str_to_tuple(s):
    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    return tuple(map(int, s.split(",")))

# ===== 노드별 탈출경로 지정 =====
ORIGINAL_GRAPHS = {
    "original_graph1.json": { # B2
        (-14,13): [(-10,13)],
        (-10,13): [(-14,13), (-6,13)],
        (-6,13): [(-10,13), (-6,9)],
        (-6,9): [(-6,13),(-6,5)],
        (-6,5): [(-6,9),(-6,1)],
        (-6,1): [(-6,5),(-6,-3),(-2,1)],
        (-6,-3): [(-6,-7),(-6,1)],
        (-6,-7): [(-6,-3)],
        (-2,1): [(-2,-3),(2,1),(-6,1)],
        (-2,-3): [(-2,1),(-2,-7)],
        (-2,-7): [(-2,-3),(-2,-11)],
        (-2,-11): [(-2,-7),(-2,-15)],
        (-2,-15): [(-2,-11),(-2,-19)],
        (-2,-19): [(-2,-15),(-2,-23)],
        (-2,-23): [(-2,-19),(-2,-27)],
        (-2,-27): [(-2,-23),(-2,-31)],
        (-2,-31): [(-2,-27),(2,-31)],
        (24,-3): [(22,1),(24,-7),(26,1)],
        (24,-7): [(24,-3),(24,-11)],
        (24,-11): [(24,-7),(24,-15)],
        (24,-15): [(24,-11),(24,-19)],
        (24,-19): [(24,-15),(24,-23)],
        (24,-23): [(24,-19),(24,-27)],
        (24,-27): [(24,-23),(22,-31)],
        (2,-31): [(-2,-31),(6,-31),(2,-35)],
        (6,-31): [(2,-31),(10,-31)],
        (10,-31): [(6,-31),(14,-31)],
        (14,-31): [(10,-31),(18,-31)],
        (18,-31): [(14,-31),(22,-31)],
        (22,-31): [(18,-31),(24,-27)],
        (2,-35): [(2,-31)],
        (2,1): [(-2,1),(6,1)],
        (6,1): [(2,1),(10,1)],
        (10,1): [(6,1),(14,1)],
        (14,1): [(10,1),(18,1)],
        (18,1): [(14,1),(22,1)],
        (18,3): [(18,1)],
        (22,1): [(18,1),(24,-3),(26,1)],
        (26,1):[(22,1),(30,1)],
        (30,1):[(26,1)]
    },
    "original_graph2.json": { # B1
        (-22,-19): [(-18,-19)],
        (-18,-19): [(-14,-19), (-18,-15), (-22,-19)],
        (-14,-19): [(-10,-19),(-18,-19)],
        (-10,-19): [(-14,-19), (-6,-19)],
        (-6,-19): [(-2,-15), (-10,-19)],
        (-18,-15): [(-18,-19),(-18,-11)],
        (-18,-11): [(-18,-15),(-18,-7)],
        (-18,-7): [(-18,-11),(-18,-3)],
        (-18,-3): [(-18,-7),(-18,1)],
        (-18,1): [(-18,5),(-18,-3)],
        (-18,5): [(-14,9),(-18,1)],
        (-14,9): [(-18,5),(-10,9)],
        (-10,9): [(-14,9),(-6,9)],
        (-6,9): [(-10,9), (-2,5)],
        (-2,-15): [(-6,-19),(-2,-11)],
        (-2,-11): [(-2,-15),(-2,-7)],
        (-2,-7): [(-2,-11),(-2,-3)],
        (-2,-3): [(-2,-7),(-2,1)],
        (-2,1): [(-2,5),(-2,-3),(2,1)],
        (-2,5): [(-2,1),(-6,9)],
        (2,1): [(-2,1), (6,1)],
        (6,1): [(2,1),(10,1)],
        (10,1): [(6,1),(14,1)],
        (14,1): [(10,1),(18,1)],
        (18,1): [(14,1),(18,5)],
        (18,5): [(18,1),(18,9),(22,5)],
        (18,9): [(18,5),(18,13),(22,9)],
        (18,13): [(18,9),(18,17),(14,13)],
        (18,17): [(18,13)],
        (14,13): [(18,13)],
        (22,5): [(26,5),(18,5)],
        (22,9): [(26,9),(18,9)],
        (26,5): [(22,9)],
        (26,9): [(22,5)]
    },
    "original_graph3.json": { # F1
        (4,13): [(4,9)],
        (4,9): [(4,13), (4,5)],
        (4,5): [(4,9), (6,1), (2,1)],
        (18,1): [(14,1)],
        (14,1): [(10,1)],
        (10,1): [(6,1)],
        (6,1): [(4,5), (2,1), (6,-3)],
        (2,1): [(4,5), (6,1)],
        (6,-3): [(6,1)]
    },
    "original_graph4.json": { # F4
        (18,1): [(14,1)],
        (14,1): [(10,1)],
        (10,1): [(6,1)],
        (6,1): [(2,1)],
        (2,1): [(-2,1)],
        (-2,1): [(-2,5),(-6,-3)],
        (-6,-3): [(-2,1)],
        (-2,5): [(-2,1),(-2,9)],
        (-2,9): [(-2,5)]
    }
}

# ====== 우선순위 지정 탈출경로 ======
TARGETS_MAP = {
    "original_graph1.json": {
        1: [(-14,13),(-6,-7),(2,-35)],  # ← 1순위 탈출구
        2: [(18,3),(30,1)]    # ← 2순위 비상계단
    },
    
    "original_graph2.json": {
        1: [(-22,-19),(18,17)],  # ← 1순위 탈출구
        2: [(14,13),(26,9),(26,5)]    # ← 2순위 비상계단
    },
    
    "original_graph3.json": {
        1: [(6,-3)],  # ← 1순위 탈출구
        2: [(4,13), (2,1)]    # ← 2순위 비상계단
    },

    "original_graph4.json": {
        1: [(-2,9),(-6,-3)]  # ← 1순위 탈출구
    }
}

# ====== 우선순위 기반 최단경로 선택 ======
def find_best_path(graph, start_node, file_key):
    """
    TARGETS_MAP[file_key] = { 1: [...], 2: [...] } 형태를 사용하여
    1순위에서 우선 최단경로를 찾고, 없으면 2순위로 내려가 선택.
    return: (best_path, found_target, priority_used, best_dist)
    """
    pri_targets = TARGETS_MAP.get(file_key, {})  # dict 또는 빈 dict
    best_dist = math.inf
    best_path = []
    found_target = None
    priority_used = None

    # 1순위 -> 2순위 ...
    for priority in sorted(pri_targets.keys()):
        # 같은 우선순위 내에서만 최단 경로 선택
        local_best_dist = math.inf
        local_best_path = []
        local_best_target = None

        for t in pri_targets[priority]:
            if t not in graph:
                continue
            d, p = bfs_shortest_path(graph, start_node, t)
            if d < local_best_dist:
                local_best_dist = d
                local_best_path = p
                local_best_target = t

        if local_best_target is not None:
            # 이 우선순위에서 경로를 찾았으면 그걸로 확정하고 즉시 종료
            best_dist = local_best_dist
            best_path = local_best_path
            found_target = local_best_target
            priority_used = priority
            break

    return best_path, found_target, priority_used, best_dist


def compute_best_path(floor: str, x: float, y: float):
    """
    (x,y) 위치에서 해당 층의 최단 경로를 계산.
    우선순위(1→2) 기반으로 목표를 선택한다.
    return: (start_node: tuple[int,int], best_path: list[tuple[int,int]])
    """
    if floor not in FLOOR_TO_GRAPH_MAP:
        raise ValueError(f"unknown floor: {floor}")
    num = FLOOR_TO_GRAPH_MAP[floor]
    if not ensure_files(num):
        raise RuntimeError("file initialization failed")

    graph = load_graph(graph_filename(num))
    file_key = original_filename(num)  # ★ 우선순위 사전 키

    # 구역 판정(겹침 시 완화)
    try:
        area = classify_area((x, y), floor, strict=True)
    except ValueError:
        area = classify_area((x, y), floor, strict=False)

    node_coord = map_area_to_node(area, floor) if area else None
    if node_coord and node_coord in graph:
        start_node = node_coord
    else:
        start_node = nearest_graph_node((x, y), graph)

    # 변경: 파일의 targets 리스트가 아니라, TARGETS_MAP(우선순위 사전) 사용
    best_path, found_target, priority_used, best_dist = find_best_path(graph, start_node, file_key)

    return start_node, best_path

# ====== 이름 잘못됐을 경우 대비 ======
_FLOOR_ALIAS = {
    "B2":"B2","B1":"B1","1F":"1F","F1":"1F","4F":"4F","F4":"4F"
}

# "B2_8" 패턴의 비콘 이름 파싱
_BEACON_NAME_RE = re.compile(r"^\s*([A-Za-z0-9]+)[_](\d+)\s*$")

def normalize_floor_token(token: str) -> str:
    return _FLOOR_ALIAS.get((token or "").strip().upper(), (token or "").strip().upper())

def parse_beacon_name(name: str):
    m = _BEACON_NAME_RE.match(name or "")
    if not m:
        raise ValueError(f"잘못된 비콘 이름 형식: {name!r}")
    floor_tok, bid = m.group(1), int(m.group(2))
    return normalize_floor_token(floor_tok), bid

# 서버에서 좌표 파싱 편의를 위한 유틸
def parse_node(value):
    if isinstance(value, str):
        return str_to_tuple(value)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (int(value[0]), int(value[1]))
    raise ValueError("node 형식이 잘못되었습니다.")

def infer_floor_from_names(names):
    # 이름 배열에서 다수결로 층 추정. 없으면 None
    counts = {}
    for n in names or []:
        try:
            f, _ = parse_beacon_name(n)
            counts[f] = counts.get(f, 0) + 1
        except Exception:
            pass
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]

# ====== 유틸 ======
def nearest_graph_node(pt, graph_dict):
    x, y = pt
    keys = list(graph_dict.keys())
    if not keys:
        raise RuntimeError("그래프 노드가 없습니다.")
    return min(keys, key=lambda n: (n[0]-x)**2 + (n[1]-y)**2)

def classify_area(pt, floor, *, strict=True):
    areas = AREAS_BY_FLOOR.get(floor, {})
    hits = [name for name, shape in areas.items() if shape(pt)]
    if not hits:
        return None
    if strict and len(hits) > 1:
        raise ValueError(f"[구역 겹침] {hits} 에 동시에 속합니다. 좌표/구역 정의 점검 요망.")
    return hits[0]

def map_area_to_node(area_name, floor):
    floor_nodes = NODES_BY_AREA.get(floor, {})
    return floor_nodes.get(area_name, None)


# ====== PATH 세트/설정 ======
PATH_SETS = {
    "4F": [(-6,-3), (-2,1), (-2,5), (-2,9), (2,1), (6,1), (10,1), (14,1), (18,1)],
    "1F": [(2,1), (4,5), (4,9), (4,13), (6,-3), (6,1), (10,1), (14,1), (18,1)],
    "B1": [
        (-22,-19), (-18,-19), (-18,-15), (-18,-11), (-18,-7), (-18,-3), (-18,1), (-18,5),
        (-14,-19), (-14,9), (-10,-19), (-10,9), (-6,-19), (-6,9), (-2,-15), (-2,-11), (-2,-7),
        (-2,-3), (-2,1), (-2,5), (2,1), (6,1), (10,1), (14,1), (14,13), (18,1), (18,5), (18,9), (18,13), (18,17),
        (22,5), (22,9), (26,5), (26,9),
    ],
    "B2": [
        (-14,13), (-10,13), (-6,13), (-6,9), (-6,5), (-6,1), (-6,-3), (-6,-7),
        (-2,-31), (-2,-27), (-2,-23), (-2,-19), (-2,-15), (-2,-11), (-2,-7), (-2,-3), (-2,1),
        (2,1), (6,1), (10,1), (14,1), (18,1), (22,1), (26,1), (30,1),
        (2,-35), (2,-31), (6,-31), (10,-31), (14,-31), (18,-31), (22,-31),
        (24,-3), (24,-7), (24,-11), (24,-15), (24,-19), (24,-23), (24,-27),
    ],
}
def set_path_floor(floor: str = "B1"):
    global PATH_NODES, NODE_XS
    if floor not in PATH_SETS:
        raise ValueError(f"알 수 없는 층: {floor} (가능: {list(PATH_SETS.keys())})")
    PATH_NODES = PATH_SETS[floor]
    NODE_XS = np.array([x for x, _ in PATH_NODES])


# ===== 공개 심볼 =====
__all__ = [
    "Rect", "rect",
    "AREAS_BY_FLOOR", "NODES_BY_AREA",
    "beacon_coords", "FLOOR_TO_GRAPH_MAP",
    "ORIGINAL_GRAPHS", "TARGETS_MAP",
    "save_graph", "load_graph", "save_targets", "load_targets", "ensure_files",
    "str_to_tuple", "nearest_graph_node", "classify_area", "map_area_to_node",
    "bfs_shortest_path",
    "AP", "Trilateration",
    "set_path_floor", "PATH_SETS",
    "trilaterate_from_top3", "compute_best_path",
    "parse_node",
    "parse_beacon_name", "infer_floor_from_names", "normalize_floor_token",
]