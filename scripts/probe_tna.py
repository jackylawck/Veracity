cat << 'EOF' > scripts/probe_tna.py
"""
The Veracity // UK TNA Discovery API Forensic Semantic Probe
主權檔案端點語意與能力全維度診斷工具：
- 嚴格型別順序：None 預檢優先於數值比對
- 零值語意解耦：區分「0==0（兩者皆無結果）」與「N==N（非零數值等價）」
- 集合論全非空前置防禦與累計獲取量截斷檢驗
- 完整窮舉所有分支，無靜默 fall-through 與誤報 CI 阻斷
"""
import sys
import json
from typing import Tuple, Dict, Any, Optional
import requests

BASE_URL = "https://discovery.nationalarchives.gov.uk/API/search/records"
USER_AGENT = "TheVeracity/2.1 (Forensic Semantic Probe; +https://jackylawck.github.io/Veracity/)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


def extract_count_and_status(data: Dict[str, Any]) -> Tuple[Optional[int], str]:
    candidate_keys = ("count", "totalResults", "total", "recordsCount", "totalRecords")
    for k in candidate_keys:
        if k in data:
            v = data[k]
            if isinstance(v, int):
                return v, f"OK ({k})"
            try:
                return int(v), f"TYPE_ANOMALY ({k} is {type(v).__name__})"
            except (ValueError, TypeError):
                return None, f"INVALID_TYPE ({k} is {type(v).__name__})"

    hits = data.get("hits")
    if isinstance(hits, dict):
        t = hits.get("total")
        if isinstance(t, int):
            return t, "OK (hits.total)"
        if isinstance(t, dict) and isinstance(t.get("value"), int):
            return t["value"], "OK (hits.total.value)"

    return None, "FIELD_ABSENT"


def execute_probe(session: requests.Session, params: Dict[str, Any], label: str) -> Dict[str, Any]:
    res = {
        "label": label, "params": params, "http_code": None, "error": None,
        "json_valid": False, "top_level_keys": [], "count_val": None,
        "count_diag": None, "records_len": 0, "record_ids": []
    }
    try:
        r = session.get(BASE_URL, params=params, headers=HEADERS, timeout=12)
        res["http_code"] = r.status_code
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            res["json_valid"] = True
            res["top_level_keys"] = list(data.keys())
            c_val, c_diag = extract_count_and_status(data)
            res["count_val"] = c_val
            res["count_diag"] = c_diag
            records = data.get("records")
            if isinstance(records, list):
                res["records_len"] = len(records)
                res["record_ids"] = [item.get("id") for item in records if isinstance(item, dict) and item.get("id")]
        else:
            res["error"] = f"Root non-dict: {type(data).__name__}"
    except Exception as e:
        res["error"] = str(e)
    return res


def run_diagnostics() -> bool:
    session = requests.Session()
    has_critical_failure = False

    print("\n" + "=" * 80)
    print("  The Veracity // UK TNA 官方端點能力與語意邊界物理診斷")
    print("=" * 80)

    # 1. 基準探針
    p_base = execute_probe(session, {"sps.searchQuery": "war", "sps.heldByFilter": "TNA", "sps.page": "0", "sps.resultsPageSize": "3"}, "基準 (全期 war)")

    # 2. 假設性解密時點參數探針
    p_rel = execute_probe(session, {
        "sps.searchQuery": "war", "sps.heldByFilter": "TNA",
        "sps.releaseStartDate": "1990-01-01", "sps.releaseEndDate": "2020-12-31",
        "sps.page": "0", "sps.resultsPageSize": "3"
    }, "假設性解密日期 (releaseStartDate)")
    p_opn = execute_probe(session, {
        "sps.searchQuery": "war", "sps.heldByFilter": "TNA",
        "sps.openingStartDate": "1990-01-01", "sps.openingEndDate": "2020-12-31",
        "sps.page": "0", "sps.resultsPageSize": "3"
    }, "假設性開放日期 (openingStartDate)")

    # 3. 涵蓋期雙視窗探針
    p_narrow = execute_probe(session, {
        "sps.searchQuery": "war", "sps.heldByFilter": "TNA",
        "sps.startDate": "1945-01-01", "sps.endDate": "1960-12-31",
        "sps.page": "0", "sps.resultsPageSize": "1"
    }, "涵蓋期窄視窗 (1945-1960)")
    p_wide = execute_probe(session, {
        "sps.searchQuery": "war", "sps.heldByFilter": "TNA",
        "sps.startDate": "1945-01-01", "sps.endDate": "1996-12-31",
        "sps.page": "0", "sps.resultsPageSize": "1"
    }, "涵蓋期寬視窗 (1945-1996)")

    # 4. 機構約束三向探針
    p_all = execute_probe(session, {"sps.searchQuery": "war", "sps.page": "0", "sps.resultsPageSize": "1"}, "全機構無限制")
    p_bl = execute_probe(session, {"sps.searchQuery": "war", "sps.heldByFilter": "BL", "sps.page": "0", "sps.resultsPageSize": "1"}, "異質機構 (BL)")

    # 5. 分頁原點探針
    p_p1 = execute_probe(session, {"sps.searchQuery": "war", "sps.heldByFilter": "TNA", "sps.page": "1", "sps.resultsPageSize": "3"}, "分頁 page=1")
    p_p2 = execute_probe(session, {"sps.searchQuery": "war", "sps.heldByFilter": "TNA", "sps.page": "2", "sps.resultsPageSize": "3"}, "分頁 page=2")

    probes = [p_base, p_rel, p_opn, p_narrow, p_wide, p_all, p_bl, p_p1, p_p2]
    for p in probes:
        print(f"\n[{p['label']}]")
        print(f"  HTTP: {p['http_code'] or 'ERR'} | 狀態: {'❌ ' + p['error'] if p['error'] else '✅ 正常'}")
        if p["json_valid"]:
            print(f"  頂層鍵名: {p['top_level_keys']}")
            print(f"  總數: {p['count_val']} ({p['count_diag']}) | records 筆數: {p['records_len']}")
            print(f"  首批 IDs: {p['record_ids'][:3]}")

    print("\n" + "=" * 80)
    print("  認識論裁決綜合報告")
    print("=" * 80)

    if not p_base["json_valid"]:
        print("❌ 核心基準端點通訊失敗，無法進行後續判定。")
        return False

    # -------------------------------------------------------------
    # 裁決 A：解密時點參數探測（含基準與目標雙 0 識別）
    # -------------------------------------------------------------
    c_base = p_base["count_val"]
    for label, p_target, c_target in [("releaseStartDate", p_rel, p_rel["count_val"]), ("openingStartDate", p_opn, p_opn["count_val"])]:
        if p_target["error"]:
            print(f"1. 解密參數 [{label}]: ❌ 端點報錯 ({p_target['error']})，非官方合法參數。")
        elif c_base is None or c_target is None:
            print(f"1. 解密參數 [{label}]: ❓ 無法比較筆數（基準 count={c_base}, 目標 count={c_target}）。")
        elif c_target == 0 and p_target["records_len"] == 0:
            if c_base == 0:
                print(f"1. 解密參數 [{label}]: ⚠️ 基準與參數查詢均為 0 筆，無法判定參數是否具備篩選效力。")
            else:
                print(f"1. 解密參數 [{label}]: ⚠️ 回傳 0 筆公文（參數被視為無匹配條件或未註冊過濾鍵）。")
        elif c_target == c_base:
            print(f"1. 解密參數 [{label}]: ❌ 筆數與基準相同 ({c_base})，API 靜默忽略該參數。")
        else:
            print(f"1. 解密參數 [{label}]: ⚠️ 筆數存在實質差異 ({c_target} != {c_base})，需進一步人工核實。")

    # -------------------------------------------------------------
    # 裁決 B：涵蓋期過濾效力（解耦 0==0 與非零相同，杜絕誤阻斷 CI）
    # -------------------------------------------------------------
    c_narrow = p_narrow["count_val"]
    c_wide = p_wide["count_val"]
    if c_narrow is not None and c_wide is not None:
        if c_narrow == 0 and c_wide == 0:
            print("2. 涵蓋期過濾: ❓ 兩個視窗均回傳 0 筆公文，無法判定參數是否生效（檢索詞可能無符合檔案）。")
        elif c_narrow < c_wide:
            print(f"2. 涵蓋期過濾: ✅ 生效（15年窗口 {c_narrow} 筆 < 51年窗口 {c_wide} 筆，sps.startDate/endDate 生效）。")
        elif c_narrow == c_wide:
            print(f"2. 涵蓋期過濾: ❌ 失效（窄寬視窗筆數均為 {c_narrow} > 0，參數遭忽略）。")
            has_critical_failure = True
        else:
            print(f"2. 涵蓋期過濾: ❌ 異常（窄視窗筆數 {c_narrow} 大於寬視窗 {c_wide}）。")
            has_critical_failure = True
    else:
        print(f"2. 涵蓋期過濾: ❓ 無法比較（診斷: narrow={p_narrow['count_diag']}, wide={p_wide['count_diag']}）。")

    # -------------------------------------------------------------
    # 裁決 C：機構約束力 (heldByFilter)（前置解耦 c_base==c_all==0）
    # -------------------------------------------------------------
    c_all = p_all["count_val"]
    c_bl = p_bl["count_val"]
    print("3. 機構過濾 (heldByFilter):")

    # 子檢驗 1：異質對照組有效性
    if c_all is None or c_bl is None:
        print(f"   - 異質對照組: ❓ 無法比較（診斷: all={p_all['count_diag']}, bl={p_bl['count_diag']}）。")
    elif c_all == 0:
        print("   - 異質對照組: ❓ 全機構無限制查詢亦返回 0 筆，無法進行機構區隔對比（檢索詞無任何庫存公文）。")
    elif c_bl == 0:
        print(f"   - 異質對照組: ⚠️ 'BL' 回傳 0 筆（全機構為 {c_all} > 0），疑似非合法典藏館代碼，無法作為對照組。")
    elif c_bl == c_all:
        print("   - 異質對照組: ❌ 靜默忽略（BL 總數等於全機構總數，heldByFilter 未生效）。")
        has_critical_failure = True
    else:
        print(f"   - 異質對照組: ℹ️ 具備區隔度（BL: {c_bl} != 全機構: {c_all}）。")

    # 子檢驗 2：TNA vs 全機構約束關係
    if c_base is not None and c_all is not None:
        if c_base == 0 and c_all == 0:
            print("   - 典藏約束力: ⚠️ TNA 與全機構查詢結果均為 0 筆，檢索詞在目標時間內無任何館藏公文。")
        elif c_base < c_all:
            print(f"   - 典藏約束力: ✅ 確證約束（TNA: {c_base} < 全機構: {c_all}）。")
        elif c_base == c_all:
            print(f"   - 典藏約束力: ⚠️ TNA 總數等於全機構總數 ({c_base})：heldByFilter 可能未生效，或該檢索詞僅存於 TNA。")
        else:
            print(f"   - 典藏約束力: ❌ 統計矛盾（TNA: {c_base} > 全機構: {c_all}）。")
            has_critical_failure = True
    else:
        print(f"   - 典藏約束力: ❓ 無法判定約束力（診斷: base={p_base['count_diag']}, all={p_all['count_diag']}）。")

    # -------------------------------------------------------------
    # 裁決 D：分頁原點拓撲（累計獲取量比對宣告總量）
    # -------------------------------------------------------------
    ids_0 = set(p_base["record_ids"])
    ids_1 = set(p_p1["record_ids"])
    ids_2 = set(p_p2["record_ids"])
    len_0, len_1, len_2 = len(ids_0), len(ids_1), len(ids_2)
    total_fetched = len_0 + len_1 + len_2

    if len_0 == 0 or len_1 == 0 or len_2 == 0:
        print(f"4. 分頁原點: ❓ 資料不足無法判定拓撲（ids_0={len_0}, ids_1={len_1}, ids_2={len_2} 筆；集合必須全部非空）。")
        if len_0 == 0 and len_1 == 0 and len_2 == 0:
            if p_base["count_val"] is not None and p_base["count_val"] > 0:
                print(f"   -> ❌ 致命：API 聲稱總量為 {p_base['count_val']} 筆，但分頁 records 回傳全為空，屬端點結構違約！")
                has_critical_failure = True
            else:
                print("   -> 警報：三組分頁探針傳回之 records 全為空（檢索詞可能無匹配公文）。")
        elif p_base["count_val"] is not None and p_base["count_val"] > total_fetched:
            print(f"   -> ⚠️ 分頁累計僅獲取 {total_fetched} 筆，但 API 聲稱總量為 {p_base['count_val']} 筆（後續分頁存在早期截斷異常）。")
    elif ids_0 == ids_1 == ids_2:
        print("4. 分頁原點: ❌ 致命：page=0, 1, 2 全部相同，API 完全忽略 page 參數。")
        has_critical_failure = True
    elif ids_0 == ids_1 and len(ids_1 & ids_2) == 0:
        print("4. 分頁原點: ⚠️ 1-based 寬容映射（page=0 與 page=1 相同，page=2 為次頁，適配器應從 1 起跳）。")
    elif len(ids_0 & ids_1) == 0 and len(ids_1 & ids_2) == 0 and len(ids_0 & ids_2) == 0:
        print("4. 分頁原點: ✅ 0-based 規範分頁（page=0, 1, 2 均非空且兩兩互斥）。")
    else:
        print(f"4. 分頁原點: ❓ 非標準分頁交集 (0∩1={len(ids_0 & ids_1)}, 1∩2={len(ids_1 & ids_2)}, 0∩2={len(ids_0 & ids_2)})，需人工排查。")

    print("=" * 80 + "\n")
    return not has_critical_failure


if __name__ == "__main__":
    success = run_diagnostics()
    sys.exit(0 if success else 1)
EOF
