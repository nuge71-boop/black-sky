import streamlit as st
import random
import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

st.set_page_config(page_title="BLACK SKY", layout="wide")

# -------------------------
# 기본 상수/설정
# -------------------------
FIELDS = ["Science", "Intel", "Security", "Economy", "PublicHealth", "Noise"]
RATINGS = ["A", "B", "C", "D"]

# 가설 후보 풀(캠페인마다 4개를 랜덤 선택해 H0~H3로 매핑)
HYP_POOL = [
    ("H_NAT", "자연적 요인(기후/서식지/먹이망 변화)"),
    ("H_HUM", "인간 요인(범죄/테러/불법 먹이 공급/오염)"),
    ("H_CROW", "까마귀 조직화(초지능/전략적 행동)"),
    ("H_INT", "정보전/심리전(조작·기만, 허위 정보 확산)"),
    ("H_BIO", "질병/병원체 요인(조류·환경성 감염)"),
    ("H_INFRA", "인프라/시스템 요인(폐기물/유통/안전 프로토콜 붕괴)"),
    ("H_INFIL", "내부 협력자/누수(정책·조사 방해, 내부 교란)"),
]

AREA_NODES = [
    ("capital", "수도권"),
    ("east_airport", "동부 공항"),
    ("west_port", "서부 항만"),
    ("north_industry", "북부 산업지대"),
    ("south_farms", "남부 곡창지대"),
    ("central_forest", "중앙 산림"),
    ("se_tourism", "남동부 관광도시"),
    ("west_hub", "서부 물류허브"),
    ("ne_base", "북동부 군사기지"),
    ("sw_fish", "남서부 어업지대"),
]
ADJ = {
    "capital": ["east_airport", "west_hub", "north_industry"],
    "east_airport": ["capital", "se_tourism", "central_forest"],
    "west_port": ["west_hub", "sw_fish"],
    "north_industry": ["capital", "ne_base"],
    "south_farms": ["central_forest", "se_tourism", "sw_fish"],
    "central_forest": ["east_airport", "south_farms"],
    "se_tourism": ["east_airport", "south_farms"],
    "west_hub": ["capital", "west_port"],
    "ne_base": ["north_industry"],
    "sw_fish": ["west_port", "south_farms"],
}

def clamp(v, lo, hi): return max(lo, min(hi, v))

# -------------------------
# 데이터 구조
# -------------------------
@dataclass
class Incident:
    id: str
    area: str
    title: str
    level: int
    timer: int
    note: str

@dataclass
class Doc:
    id: str
    field: str
    area: str
    title: str
    summary: str
    # 실제 진실/기만을 위한 내부 속성
    truth_tags: List[str]      # 실제로 어떤 가설을 지지하는지 (예: ["H_CROW"])
    veracity: float            # 0~1 문서 진실도(부분진실 포함)
    planted: bool              # 적(까마귀)이 의도적으로 심었는지

@dataclass
class InvestigationJob:
    kind: str                  # "Lab"|"Agency"|"Audit"
    target: str                # cluster_id or doc_id
    eta: int                   # 남은 턴
    cost: int                  # IP 비용(이 턴에서 지불)
    result: Optional[str] = None

# -------------------------
# 캠페인 초기화
# -------------------------
def new_campaign():
    # 상태
    st.session_state.week = 1
    st.session_state.metrics = {
        "trust": 70.0,
        "fear": 20.0,
        "economy": 65.0,
        "order": 72.0,
        "food": 70.0,
        "infra": 70.0,
        "intel": 50.0,
    }
    st.session_state.opinion = {  # 4그룹 비율(사건에 따라 변동)
        "stability": 34.0,
        "pragmatic": 41.0,
        "liberty": 15.0,
        "conspir": 10.0,
    }

    # 투자(IP): “총합 0” 분배 + 매 턴 기본 포인트
    st.session_state.ip_base = 6
    st.session_state.ip_event = 0
    st.session_state.invest = {k: 0 for k in FIELDS}

    # 가설(캠페인 랜덤)
    picks = random.sample(HYP_POOL, 4)
    st.session_state.hyp_map = {f"H{i}": picks[i] for i in range(4)}  # H0..H3 -> (code, label)
    # 진짜 정체(정답)는 무조건 H_CROW 포함되게 강제 (게임 테마 고정)
    # 만약 뽑힌 4개에 H_CROW가 없다면 하나를 교체
    if all(code != "H_CROW" for code, _ in st.session_state.hyp_map.values()):
        replace_key = random.choice(["H0","H1","H2","H3"])
        st.session_state.hyp_map[replace_key] = next(x for x in HYP_POOL if x[0] == "H_CROW")

    # 내부 정답: 캠페인에서 "까마귀 초지능"이 정체
    st.session_state.true_identity = "H_CROW"

    # 가설 확률(초기 균등)
    st.session_state.hyp_prob = {k: 25.0 for k in ["H0","H1","H2","H3"]}

    # 사건 초기
    st.session_state.incidents = [
        Incident(id="inc1", area="east_airport", title="버드스트라이크 급증", level=1, timer=2, note="최근 3일 7건"),
        Incident(id="inc2", area="south_farms", title="작물 피해 증가", level=1, timer=3, note="원인 미확인"),
        Incident(id="inc3", area="central_forest", title="대규모 집단 관찰", level=1, timer=3, note="개체수 증가"),
    ]

    # 문서/분류/클러스터
    st.session_state.doc_seq = 1
    st.session_state.docs: List[Doc] = []
    st.session_state.doc_rating: Dict[str, str] = {}   # doc_id -> A/B/C/D (플레이어 분류)
    st.session_state.clusters = {
        "C1": {"title":"클러스터 1", "doc_ids": [], "rationale": ""},
        "C2": {"title":"클러스터 2", "doc_ids": [], "rationale": ""},
        "C3": {"title":"클러스터 3", "doc_ids": [], "rationale": ""},
    }

    # 조사 큐
    st.session_state.jobs: List[InvestigationJob] = []

    # 로그
    st.session_state.log = [f"Week 1 시작: 캠페인 가설이 설정됨."]

    # 첫 턴 문서 생성
    st.session_state.docs = generate_docs()

def current_ip_total() -> Tuple[int,int]:
    m = st.session_state.metrics
    econ_bonus = int(m["economy"] // 20)  # 0~5
    econ_bonus = clamp(econ_bonus, -2, 6)
    total = st.session_state.ip_base + econ_bonus + st.session_state.ip_event
    return total, econ_bonus

# -------------------------
# 적응형 문서 생성(부분진실/기만)
# -------------------------
def quality_from_invest(field: str) -> float:
    """
    투자 총합 0 규칙에서:
    + 투자면 해당 분야 문서 품질/속도 증가
    - 투자면 혼탁/지연/루머 영향 증가
    """
    v = st.session_state.invest.get(field, 0)
    # -6~+6 범위 가정
    return clamp(0.15 + 0.12 * v, 0.05, 0.95)

def crow_deception_pressure() -> float:
    """
    까마귀의 기만 강도: 플레이어가 뭘 중시하는지 역이용.
    intel/science가 낮으면 루머/심리전이 먹힘.
    """
    m = st.session_state.metrics
    inv = st.session_state.invest
    base = 0.45
    base += 0.10 * (60 - m["intel"]) / 60.0
    base += 0.08 * (-(inv.get("Intel",0)))/6.0
    base += 0.06 * (-(inv.get("Science",0)))/6.0
    return clamp(base, 0.15, 0.85)

def pick_area_weighted() -> str:
    # 사건이 있는 지역 주변에서 문서가 더 잘 뜨도록
    inc_areas = [i.area for i in st.session_state.incidents]
    pool = []
    for a,_ in AREA_NODES:
        w = 1
        if a in inc_areas: w += 3
        if any(a in ADJ.get(x,[]) for x in inc_areas): w += 1
        pool += [a]*w
    return random.choice(pool)

def generate_docs() -> List[Doc]:
    docs = []
    dec = crow_deception_pressure()

    # 각 분야별 1~2개 문서
    for field in FIELDS:
        n = 1 + (1 if random.random() < 0.35 else 0)
        q = quality_from_invest(field)

        for _ in range(n):
            area = pick_area_weighted()
            did = f"D{st.session_state.doc_seq}"
            st.session_state.doc_seq += 1

            # 진실 태그(내부적으로 어떤 가설을 지지하는가)
            # - Science/Intel/Security는 진실 문서 비율 높음(투자+일수록 더)
            # - Noise는 부분진실/허위 비율 높음
            planted = False
            veracity = q

            # 기만 문서 생성 여부
            if random.random() < dec:
                # 플레이어가 분류를 헷갈리게 만드는 "부분진실" 투입
                planted = True if random.random() < 0.6 else False
                # 부분진실은 veracity는 중간인데 결론이 다른 가설로 유도
                veracity = clamp(0.35 + 0.30 * random.random(), 0.10, 0.75)

            # 어떤 가설에 연결되는지 결정
            # 진실(까마귀) 단서도 섞되, 다른 단서도 계속 나와서 혼란 유지
            hyp_keys = ["H0","H1","H2","H3"]
            # 실제 정체(H_CROW)가 포함된 가설키 찾기
            crow_key = None
            for k,(code,_) in st.session_state.hyp_map.items():
                if code == "H_CROW":
                    crow_key = k
                    break

            # 기본은 랜덤 가설로 연결
            tag_key = random.choice(hyp_keys)

            # Science/Intel 투자가 높을수록 crow_key 단서가 더 자주 등장
            if crow_key and field in ["Science","Intel"] and random.random() < (0.20 + 0.08*max(0, st.session_state.invest.get(field,0))):
                tag_key = crow_key

            # Noise는 기만일 때 crow_key가 아닌 쪽으로 유도하기 쉬움
            if planted and field == "Noise" and crow_key:
                if random.random() < 0.7:
                    tag_key = random.choice([k for k in hyp_keys if k != crow_key])

            truth_tags = [tag_key]

            title, summary = make_doc_text(field, area, truth_tags[0], veracity, planted)

            docs.append(Doc(
                id=did, field=field, area=area,
                title=title, summary=summary,
                truth_tags=truth_tags, veracity=veracity, planted=planted
            ))

    return docs

def make_doc_text(field: str, area: str, hyp_key: str, veracity: float, planted: bool) -> Tuple[str,str]:
    area_name = dict(AREA_NODES)[area]
    hyp_label = st.session_state.hyp_map[hyp_key][1]

    # 표면 텍스트는 “그럴듯”하게 만들되, veracity/ planted에 따라 뉘앙스 다르게
    if field == "Noise":
        title = f"{area_name} 커뮤니티 영상/루머 확산"
        base = f"민간 채널에서 '{hyp_label}'을(를) 암시하는 주장. 근거는 단편적."
        if planted:
            base += " 확산 속도가 비정상적으로 빠름."
    elif field == "Science":
        title = f"기초과학 메모: 패턴/행동 서명 분석"
        base = f"관찰 패턴이 '{hyp_label}' 가설과 일부 부합. 데이터는 제한적."
    elif field == "Intel":
        title = f"정보기관 요약: 키워드/동향 모니터링"
        base = f"여러 채널에서 '{hyp_label}' 관련 신호가 증가. 출처 신뢰도 혼재."
    elif field == "Security":
        title = f"치안/안전 보고: 반복 사건의 공통점"
        base = f"현장 기록에서 '{hyp_label}' 가능성을 시사하는 징후. 단일원인 단정은 금물."
    elif field == "Economy":
        title = f"경제 브리핑: 공급망/보험/가격 이상"
        base = f"지표 변화가 '{hyp_label}' 시나리오와 연결될 수 있음. 인과는 불명확."
    else:  # PublicHealth
        title = f"보건/환경 메모: 위생·오염·생태 영향"
        base = f"환경 지표가 '{hyp_label}'과(와) 상관을 보일 수 있음. 추가 조사 필요."

    # veracity 표현(플레이어는 직접 veracity를 못 봄)
    if veracity > 0.75:
        base += " (정밀 기록/출처 다양)"
    elif veracity > 0.45:
        base += " (부분 일치/추가 검증 필요)"
    else:
        base += " (불완전/상충 정보 다수)"

    return title, base

# -------------------------
# 클러스터/연속성 점수
# -------------------------
def cluster_score(doc_ids: List[str], rationale: str) -> Dict[str,float]:
    docs_by_id = {d.id: d for d in st.session_state.docs}
    picked = [docs_by_id[x] for x in doc_ids if x in docs_by_id]
    if not picked:
        return {"continuity": 0.0, "source_div": 0.0, "rating_w": 0.0}

    # 지역/시간은 단순화(지역 유사성)
    areas = [d.area for d in picked]
    area_score = 1.0 if len(set(areas)) == 1 else 0.6 if len(set(areas)) == 2 else 0.3

    # 출처 다양성
    fields = [d.field for d in picked]
    source_div = len(set(fields)) / max(1, len(FIELDS))

    # 플레이어 신뢰도 분류 가중
    w_map = {"A":1.0, "B":0.7, "C":0.35, "D":0.15}
    rating_w = 0.0
    for d in picked:
        r = st.session_state.doc_rating.get(d.id, "C")
        rating_w += w_map.get(r, 0.35)
    rating_w = rating_w / len(picked)

    # rationale이 비어있으면 continuity 약화
    rationale_boost = 1.0 if (rationale.strip() and len(rationale.strip()) >= 6) else 0.85

    continuity = clamp((0.45*area_score + 0.35*rating_w + 0.20*source_div) * rationale_boost, 0.0, 1.0)
    return {"continuity": continuity, "source_div": source_div, "rating_w": rating_w}

# -------------------------
# 조사 의뢰(큐)
# -------------------------
def can_afford(cost: int) -> bool:
    ip_total, _ = current_ip_total()
    # 비용은 "안전 포인트"에서만 사용(= ip_total)로 처리
    return cost <= ip_total

def enqueue_job(kind: str, target: str, cost: int, eta: int):
    st.session_state.jobs.append(InvestigationJob(kind=kind, target=target, cost=cost, eta=eta))
    st.session_state.log.append(f"조사 의뢰: {kind} → {target} (ETA {eta}턴, 비용 {cost})")

def resolve_job(job: InvestigationJob) -> str:
    """
    결과는 간단 MVP: 진실/기만을 '확률적으로' 드러냄.
    - Lab: 클러스터의 연관 가능성/우세 가설 힌트
    - Agency: 문서 진위/조작 흔적
    - Audit: 내부 혼탁 위험도(기만 압력) 힌트
    """
    docs_by_id = {d.id: d for d in st.session_state.docs}
    if job.kind == "Lab":
        c = st.session_state.clusters.get(job.target)
        if not c:
            return "연구소: 대상 클러스터를 찾지 못함."
        sc = cluster_score(c["doc_ids"], c["rationale"])
        # 우세 가설 추정(클러스터 문서의 truth_tags 기반, 단 veracity로 가중)
        counts = {k:0.0 for k in ["H0","H1","H2","H3"]}
        for did in c["doc_ids"]:
            d = docs_by_id.get(did)
            if not d: continue
            k = d.truth_tags[0]
            counts[k] += d.veracity
        best = max(counts, key=lambda x: counts[x])
        label = st.session_state.hyp_map[best][1]
        pct = int(40 + 50*sc["continuity"])  # 40~90
        return f"연구소: 클러스터 연관 가능성 {pct}% · 우세 가설 힌트: {label}"
    elif job.kind == "Agency":
        d = docs_by_id.get(job.target)
        if not d:
            return "비밀기관: 대상 문서를 찾지 못함."
        # planted면 조작 흔적이 더 잘 잡힘(다만 Intel 투자 낮으면 실패)
        intel_q = quality_from_invest("Intel")
        detect = 0.35 + 0.55*intel_q
        if d.planted and random.random() < detect:
            return f"비밀기관: {d.id} 문서에서 조작/유도 흔적 가능성 높음."
        if (not d.planted) and random.random() < (0.25 + 0.55*intel_q):
            return f"비밀기관: {d.id} 문서는 실재 기록과 대체로 부합."
        return f"비밀기관: {d.id} 문서의 실재성 판단 보류(상충 단서)."
    else:  # Audit
        p = crow_deception_pressure()
        risk = int(30 + 70*p)  # 40~90쯤
        return f"내부감사: 정보 혼탁/누수 위험도 {risk}/100 · 보고 체계 점검 권고."

def tick_jobs_and_apply_costs():
    # 비용은 이 턴 ip_total 안에서만 지불(단순화)
    ip_total, _ = current_ip_total()
    spent = 0
    # 이번 턴 결제되지 못하면 job을 실행 못하게 하는 대신, 생성 자체를 막는 UX를 사용(버튼 disabled)
    # 여기서는 턴 넘어갈 때 '진행 중' job의 eta만 감소
    for j in st.session_state.jobs:
        if j.result is None:
            j.eta -= 1
            if j.eta <= 0:
                j.result = resolve_job(j)
                st.session_state.log.append(f"조사 결과: {j.result}")

# -------------------------
# 가설 확률 업데이트
# -------------------------
def update_hypotheses_from_player_actions():
    """
    플레이어 분류/클러스터/조사 결과에 의해 hyp_prob이 조금씩 이동.
    단, 기만 문서를 A로 올려치면 오히려 틀린 가설이 강화될 수 있음.
    """
    docs_by_id = {d.id: d for d in st.session_state.docs}
    prob = st.session_state.hyp_prob

    # 1) 문서 분류(가중)
    w_map = {"A":1.2, "B":0.8, "C":0.35, "D":0.15}
    for d in st.session_state.docs:
        r = st.session_state.doc_rating.get(d.id, "C")
        w = w_map.get(r, 0.35)
        # planted & A면 오히려 잘못 유도될 확률이 큼(부분진실/왜곡)
        if d.planted and r == "A":
            w *= 1.35
        k = d.truth_tags[0]
        prob[k] += 0.25 * w

    # 2) 클러스터 연속성(높으면 더 크게 이동)
    for cid, c in st.session_state.clusters.items():
        sc = cluster_score(c["doc_ids"], c["rationale"])
        if sc["continuity"] <= 0.0:
            continue
        # 우세 가설(클러스터 기반)
        counts = {k:0.0 for k in ["H0","H1","H2","H3"]}
        for did in c["doc_ids"]:
            d = docs_by_id.get(did)
            if not d: continue
            k = d.truth_tags[0]
            counts[k] += d.veracity
        best = max(counts, key=lambda x: counts[x])
        prob[best] += 2.0 * sc["continuity"]

    # 3) 조사 결과 텍스트 파싱(간단)
    for j in st.session_state.jobs:
        if not j.result:
            continue
        if "우세 가설 힌트:" in j.result:
            # 라벨 일치하는 hyp_key 찾기
            hint_label = j.result.split("우세 가설 힌트:")[-1].strip()
            for k, (_, label) in st.session_state.hyp_map.items():
                if label == hint_label:
                    prob[k] += 4.0
        if "조작/유도 흔적" in j.result:
            # 정보전/내부 누수 가설이 있으면 강화
            for k, (code, _) in st.session_state.hyp_map.items():
                if code in ["H_INT", "H_INFIL"]:
                    prob[k] += 2.0

    # 정규화
    total = sum(prob.values())
    for k in prob:
        prob[k] = 100.0 * prob[k] / total

# -------------------------
# 시간 압박: 사건 악화/확산
# -------------------------
def escalate_and_spread():
    m = st.session_state.metrics
    # 투자 -Security이면 악화가 더 빠름
    sec_penalty = max(0, -st.session_state.invest.get("Security", 0))
    for inc in st.session_state.incidents:
        inc.timer -= 1 + (1 if sec_penalty >= 3 and random.random() < 0.35 else 0)
        if inc.timer <= 0:
            inc.level = clamp(inc.level + 1, 1, 5)
            inc.timer = clamp(3 - (inc.level // 2), 1, 3)
            m["fear"] = clamp(m["fear"] + 3.5, 0, 100)
            m["trust"] = clamp(m["trust"] - 2.0, 0, 100)

            # 확산(높은 레벨에서 인접 지역으로 새 사건 생성)
            if inc.level >= 3 and random.random() < 0.35:
                nbrs = ADJ.get(inc.area, [])
                if nbrs:
                    to = random.choice(nbrs)
                    new_id = f"inc{random.randint(100,999)}"
                    st.session_state.incidents.append(
                        Incident(id=new_id, area=to, title="연쇄 사건 징후", level=1, timer=3, note="원인 불명확")
                    )
                    m["fear"] = clamp(m["fear"] + 1.5, 0, 100)

    # 경제/인프라 비용
    worst = max([i.level for i in st.session_state.incidents]) if st.session_state.incidents else 1
    m["infra"] = clamp(m["infra"] - 0.9*(worst-1), 0, 100)
    m["economy"] = clamp(m["economy"] - 0.7*(worst-1), 0, 100)
    if any(i.area == "south_farms" and i.level >= 3 for i in st.session_state.incidents):
        m["food"] = clamp(m["food"] - 1.2, 0, 100)

# -------------------------
# 여론 이동
# -------------------------
def update_opinion():
    m = st.session_state.metrics
    op = st.session_state.opinion

    fear = m["fear"]
    trust = m["trust"]

    # 공포↑ -> 안정추구↑, 실용↓
    delta = (fear - 20) * 0.03
    op["stability"] = clamp(op["stability"] + delta, 10, 75)
    op["pragmatic"] = clamp(op["pragmatic"] - delta, 10, 75)

    # 신뢰↓ -> 음모론↑, 자유↑
    if trust < 55:
        op["conspir"] = clamp(op["conspir"] + 1.0, 0, 40)
        op["liberty"] = clamp(op["liberty"] + 0.6, 0, 40)

    # 정규화
    total = sum(op.values())
    for k in op:
        op[k] = 100.0 * op[k] / total

# -------------------------
# 승리/패배 판정
# -------------------------
def check_collapse() -> bool:
    m = st.session_state.metrics
    return (m["trust"] <= 0) or (m["order"] <= 0) or (m["economy"] <= 0) or (m["infra"] <= 0)

def identity_declared_correct(declared_key: str) -> bool:
    # declared_key는 H0~H3 중 하나
    code, _ = st.session_state.hyp_map[declared_key]
    return code == st.session_state.true_identity

def evidence_threshold_met(declared_key: str) -> bool:
    # “정체를 밝혀냄”을 너무 쉽게 만들지 않기 위해:
    # - 확률 70% 이상
    # - 그리고 연구소(Lab) 결과가 1회 이상 있어야 함(근거 확보)
    prob = st.session_state.hyp_prob.get(declared_key, 0.0)
    has_lab = any(j.result and j.kind == "Lab" for j in st.session_state.jobs)
    return (prob >= 70.0) and has_lab

# -------------------------
# 턴 진행
# -------------------------
def next_turn():
    # 1) 조사 큐 진행
    tick_jobs_and_apply_costs()

    # 2) 사건 악화/확산(시간 압박)
    escalate_and_spread()

    # 3) 여론 변화
    update_opinion()

    # 4) 가설 업데이트(플레이어 행동 반영)
    update_hypotheses_from_player_actions()

    # 5) 다음 주 문서 생성
    st.session_state.week += 1
    st.session_state.docs = generate_docs()

    st.session_state.log.append(f"Week {st.session_state.week} 시작 (사건 {len(st.session_state.incidents)}개)")

# -------------------------
# UI 구성
# -------------------------
if "week" not in st.session_state:
    new_campaign()

st.title("BLACK SKY — 문서/클러스터/가설 전략")
st.caption("목표: 초지능 까마귀가 만든 판에서, 근거를 쌓아 ‘정체’를 밝혀 승리한다.")

# 상단: 캠페인 제어
top_l, top_r = st.columns([1,1])
with top_l:
    if st.button("🔄 새 캠페인 시작"):
        new_campaign()
        st.rerun()
with top_r:
    ip_total, econ_bonus = current_ip_total()
    st.info(f"Week {st.session_state.week} · 안전 IP {ip_total} (경제 보정 {econ_bonus:+d}) · 투자 합계는 항상 0이 되게 조정하세요.")

# 1) 좌: 지도/사건 / 우: 국가 지표+여론
left, right = st.columns([1.35, 1.0], gap="large")
with left:
    st.subheader("🗺️ 사건(시간 압박)")
    area_name = dict(AREA_NODES)
    for inc in st.session_state.incidents[:8]:
        st.write(f"• **{area_name[inc.area]}** — {inc.title} | 레벨 **{inc.level}** | 악화까지 **{inc.timer}**턴 · {inc.note}")
    if len(st.session_state.incidents) > 8:
        st.write(f"(+ {len(st.session_state.incidents)-8}개 더 있음)")

with right:
    st.subheader("📊 국가 지표")
    m = st.session_state.metrics
    c1, c2 = st.columns(2)
    with c1:
        st.metric("정부 신뢰", int(m["trust"]))
        st.metric("사회 질서", int(m["order"]))
        st.metric("경제력", int(m["economy"]))
        st.metric("공포", int(m["fear"]))
    with c2:
        st.metric("인프라", int(m["infra"]))
        st.metric("식량", int(m["food"]))
        st.metric("정보력", int(m["intel"]))
    st.subheader("🧭 여론 분포(사건에 따라 변동)")
    op = st.session_state.opinion
    st.write(f"안정추구 {op['stability']:.1f}% · 실용 {op['pragmatic']:.1f}% · 자유우선 {op['liberty']:.1f}% · 음모론 {op['conspir']:.1f}%")

st.divider()

# 2) 투자: 총합 0 분배
st.subheader("💰 투자(총합 0 분배)")
st.caption("기본 IP는 ‘안전하게 쓸 수 있는 여력’이고, 투자(-)는 다른 분야를 희생해서 끌어오는 구조입니다. 음수는 후폭풍이 큽니다.")
inv_cols = st.columns(6)
tmp = {}
for i, f in enumerate(FIELDS):
    with inv_cols[i]:
        tmp[f] = st.slider(f, -6, 6, int(st.session_state.invest.get(f,0)), 1)
sum_inv = sum(tmp.values())
if sum_inv != 0:
    st.warning(f"현재 투자 합계가 {sum_inv} 입니다. **합계가 0**이 되도록 조정해야 턴 종료가 가능합니다.")
else:
    st.success("투자 합계 0 OK")
st.session_state.invest = tmp

st.divider()

# 3) 가설 보드(캠페인 랜덤)
st.subheader("🧩 가설 경쟁(캠페인 랜덤)")
hyp_cols = st.columns(4)
for i, k in enumerate(["H0","H1","H2","H3"]):
    code, label = st.session_state.hyp_map[k]
    with hyp_cols[i]:
        st.markdown(f"**{k}**")
        st.write(label)
        st.progress(min(1.0, st.session_state.hyp_prob[k]/100.0))
        st.write(f"{st.session_state.hyp_prob[k]:.1f}%")

st.caption("‘정체 선언’은 확률만으로는 부족합니다. **연구소(Lab) 결과**로 근거를 확보해야 합니다.")

declare_col1, declare_col2 = st.columns([1,2])
with declare_col1:
    declared = st.selectbox("정체 선언(가설 선택)", ["H0","H1","H2","H3"])
with declare_col2:
    if st.button("🏁 정체 선언(승리 조건 체크)"):
        if evidence_threshold_met(declared):
            if identity_declared_correct(declared):
                st.success("🎉 승리! 까마귀의 정체(초지능 조직화)를 밝혀냈다.")
                st.stop()
            else:
                # 오판 페널티: 신뢰 하락 + 공포 증가
                st.session_state.metrics["trust"] = clamp(st.session_state.metrics["trust"] - 12, 0, 100)
                st.session_state.metrics["fear"] = clamp(st.session_state.metrics["fear"] + 10, 0, 100)
                st.session_state.log.append("정체 선언 실패: 오판으로 정부 신뢰 급락/공포 상승.")
                st.error("❌ 정체 선언 실패. 사회가 더 불안정해졌다.")
        else:
            st.warning("근거가 부족합니다. (조건: 해당 가설 70%+ & 연구소 결과 1회 이상)")

st.divider()

# 4) 문서 보드 + 신뢰도 분류
st.subheader("📄 문서 보드(A/B/C/D 분류)")
st.caption("문서는 ‘부분진실’이 섞여 있을 수 있습니다. A로 올려치면 기만에 취약해집니다.")

docs = st.session_state.docs
docs_by_id = {d.id: d for d in docs}
show_cols = st.columns(2)
with show_cols[0]:
    st.write("**문서 목록**")
with show_cols[1]:
    st.write("**분류(A/B/C/D)**")

for d in docs[:14]:
    cL, cR = st.columns([3,1])
    with cL:
        area_name = dict(AREA_NODES)[d.area]
        st.markdown(f"**{d.id}** · {d.field} · {area_name}")
        st.write(d.title)
        st.write(d.summary)
    with cR:
        st.session_state.doc_rating[d.id] = st.selectbox(
            f"{d.id} 분류",
            RATINGS,
            index=RATINGS.index(st.session_state.doc_rating.get(d.id, "C")),
            key=f"rate_{d.id}"
        )

st.divider()

# 5) 클러스터(3개): 문서 묶음 + 논리 + 점수
st.subheader("🧷 사건 묶음(클러스터 3개)")
st.caption("문서들을 묶고, ‘연속성 이유’를 써서 점수를 올리세요. 점수가 높으면 가설/조사 효율이 증가합니다.")

all_doc_ids = [d.id for d in docs]
cluster_cols = st.columns(3)
for idx, cid in enumerate(["C1","C2","C3"]):
    with cluster_cols[idx]:
        st.markdown(f"### {st.session_state.clusters[cid]['title']}")
        chosen = st.multiselect(
            "문서 선택",
            options=all_doc_ids,
            default=st.session_state.clusters[cid]["doc_ids"],
            key=f"cl_{cid}"
        )
        st.session_state.clusters[cid]["doc_ids"] = chosen
        st.session_state.clusters[cid]["rationale"] = st.text_area(
            "연속성 이유(짧게)",
            value=st.session_state.clusters[cid]["rationale"],
            key=f"ra_{cid}",
            height=80
        )
        sc = cluster_score(chosen, st.session_state.clusters[cid]["rationale"])
        st.write(f"연속성: **{sc['continuity']:.2f}** · 출처다양성: {sc['source_div']:.2f} · 분류가중: {sc['rating_w']:.2f}")

st.divider()

# 6) 조사 의뢰(연구소/비밀기관/내부감사)
st.subheader("🧪 조사 의뢰(턴 기반 큐)")
st.caption("연구소=클러스터 연관성 검증 / 비밀기관=문서 실재성 / 내부감사=정보 혼탁·누수 위험")

j1, j2, j3 = st.columns(3)

with j1:
    st.markdown("**연구소(Lab)**")
    target_c = st.selectbox("대상 클러스터", ["C1","C2","C3"])
    cost, eta = 3, 2
    disabled = (sum_inv != 0) or (not can_afford(cost))
    if st.button(f"의뢰(비용 {cost}, ETA {eta})", disabled=disabled):
        enqueue_job("Lab", target_c, cost=cost, eta=eta)

with j2:
    st.markdown("**비밀기관(Agency)**")
    target_d = st.selectbox("대상 문서", all_doc_ids)
    cost, eta = 2, 1
    disabled = (sum_inv != 0) or (not can_afford(cost))
    if st.button(f"의뢰(비용 {cost}, ETA {eta})", disabled=disabled, key="ag_btn"):
        enqueue_job("Agency", target_d, cost=cost, eta=eta)

with j3:
    st.markdown("**내부감사(Audit)**")
    cost, eta = 2, 2
    disabled = (sum_inv != 0) or (not can_afford(cost))
    if st.button(f"의뢰(비용 {cost}, ETA {eta})", disabled=disabled, key="au_btn"):
        enqueue_job("Audit", "system", cost=cost, eta=eta)

# 조사 큐 표시
if st.session_state.jobs:
    st.write("**진행 중/완료 조사**")
    for j in st.session_state.jobs[-8:]:
        status = "완료" if j.result else f"ETA {j.eta}"
        st.write(f"- [{status}] {j.kind} → {j.target} | {j.result or ''}")

st.divider()

# 7) 턴 종료
turn_col1, turn_col2 = st.columns([1,2])
with turn_col1:
    if st.button("⏭️ 턴 종료(다음 주로)", disabled=(sum_inv != 0)):
        next_turn()
        # 붕괴 체크
        if check_collapse():
            st.error("💀 국가 붕괴. 원인은 끝까지 ‘단일 원인’으로 수렴하지 않는다…")
            st.stop()
        st.rerun()

with turn_col2:
    st.write("턴 종료 전 체크: (1) 투자 합계 0 (2) 문서 분류/클러스터/조사 전략 결정")

# 로그
st.subheader("📝 로그")
for line in reversed(st.session_state.log[-18:]):
    st.write("• " + line)
