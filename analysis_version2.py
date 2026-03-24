import json
from collections import defaultdict
import time
from collections import Counter

# 讀取遊戲資料
def read_game_data(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
    
# 提取所有玩家的已知牌
def extract_known_tiles(data):
    known_tiles = []
    dora_tiles = [tile for tile in data.get("dora", []) if tile != "back"]
    known_tiles += dora_tiles
    for pid in ["1", "2", "3", "4"]:
        player = data["players"][pid] 
        known_tiles += player.get("discarded", [])
        # known_tiles += player.get("hand", [])
        
        for tile in known_tiles:
            if tile.endswith("_R") and tile[:-2][-1] == "5":
                known_tiles.append(tile[:-2])  # 加上額外的普通 5 號牌（如 Wan_5）
        for meld in player.get("melds", []):
            if isinstance(meld, str):
                known_tiles.append(meld)
            elif isinstance(meld, dict) and "tiles" in meld:
                known_tiles += meld["tiles"]
    
    return known_tiles

def adjust_based_on_sequence_rules(tile, player_discards):
    # 適用於數牌（萬、索、筒）
    if not any(c.isdigit() for c in tile):
        return 1.0

    num = int(''.join(filter(str.isdigit, tile)))
    suit = ''.join(filter(str.isalpha, tile))
    
    adjustment = 1.0

    # 147 型：打出1、4、7會降低對其他兩張的需求
    related_147 = {
        1: [4],
        4: [1, 7],
        7: [4]
    }

    # 258 型（多為搭子也可跳過，但可拓展使用）
    related_258 = {
        2: [5],
        5: [2, 8],
        8: [5]
    }

    # 369 型
    related_369 = {
        3: [6],
        6: [3, 9],
        9: [6]
    }

    all_related = {**related_147, **related_258, **related_369}

    if num in all_related:
        for related_num in all_related[num]:
            related_tile = f"{suit}{related_num}"
            # 檢查是否打出過這些相關的牌
            if any(related_tile in discard for discard in player_discards):
                adjustment *= 0.9  # 危險度下降一點

    return adjustment

# 計算剩餘牌
def calculate_remaining_tiles(all_tiles, known_tiles):
    remaining_tiles = {tile: all_tiles.get(tile, 0) for tile in all_tiles}
    for tile in known_tiles:
        if tile in remaining_tiles:
            remaining_tiles[tile] -= 1
    remaining_tiles = {tile: count for tile, count in remaining_tiles.items() if count > 0}
    return remaining_tiles

def analyze_discard_behavior(player):
    discards = player.get("discarded", [])
    melds = player.get("melds", [])

    num_middle_discards = 0  # 中張牌（4~6）
    num_terminal_discards = 0  # 1、9
    num_honor_discards = 0  # 字牌

    for t in discards:
        if not any(c.isdigit() for c in t):
            num_honor_discards += 1
            continue
        n = int(''.join(filter(str.isdigit, t)))
        if n in [1, 9]:
            num_terminal_discards += 1
        elif n in [4, 5, 6]:
            num_middle_discards += 1

    multiplier = 1.0

    if len(melds) >=  12:
        multiplier += 3.0  # 多副露 → 快速型
    elif len(melds) < 12 and len(melds) >= 9:
        multiplier += 2.5
    elif len(melds) < 9 and len(melds) >= 6:
        multiplier += 2.0
    elif len(melds) <= 4 and len(melds) >=3:
        multiplier += 1.5
    elif len(melds) == 0 and not player.get("Riichi", False):
        multiplier += 1.0  # 沒副露、沒立直 → 機率降低

    multiplier += num_middle_discards*0.2  # 中張都丟出 → 可能已經形聽

    return multiplier


def predict_tenpai(data, remaining_tiles):

    tenpai_info = {}
    for pid in ["2", "3", "4"]:
        player = data["players"][pid]
        round_wind = data["field_wind"]
        player_seat_wind = player.get("Wind")
        discarded_set = set(player.get("discarded", []))
        melds = player.get("melds", [])
        is_riichi = player.get("Riichi", False)

        is_riichi = str(is_riichi).lower() == "true"

        wait_tiles = {}

        #分析棄牌行為倍率
        behavior_multiplier = analyze_discard_behavior(player)

        if is_riichi:
            tenpai_prob = 100
        else:
            turn = len(player.get("discarded", []))  # 巡目（出過幾張牌）
            if turn == 0:
                tenpai_prob = 0.0
            else:
                # 修改巡目係數計算方式，使早巡的機率更低
                turn_factor = min(turn / 18, 1.0)  # 正規化：第18巡以上視為1.0
                # 降低早巡的基礎機率，並使用更陡峭的曲線
                base_probability = 20  # 降低基礎機率
                turn_multiplier = turn_factor ** 1.5  # 使用指數增長
                tenpai_prob = behavior_multiplier * base_probability * (0.8 * turn_multiplier)
                if (turn/6)<1:
                    tenpai_prob*=1.25
                elif (turn/6)<2:
                    tenpai_prob*=2.0
                elif (turn/6)>=2:
                    tenpai_prob*=2.5
                tenpai_prob = max(0, min(round(tenpai_prob, 2), 95))

        candidate_tiles = {
        tile: count for tile, count in remaining_tiles.items()
        if tile not in discarded_set
    }
        #高機率聽牌才分析等牌
 
        for tile, count in candidate_tiles.items():
                score = (count**0.5)*2  # 基礎分數為剩餘張數

                suit_count = {"Wan": 0, "Tong": 0, "Tiao": 0}
                for t in player.get("discarded", []):
                    if t.startswith("Wan"):
                        suit_count["Wan"] += 1
                    elif t.startswith("Tong"):
                        suit_count["Tong"] += 1
                    elif t.startswith("Tiao"):
                        suit_count["Tiao"] += 1

                score *= adjust_based_on_sequence_rules(tile, player.get("discarded", []))

                # 自風與場風加成（字牌）
                if tile.startswith("Feng"):
                    if tile == round_wind and tile == player_seat_wind:
                        score *= 1.15 * 1.15
                    elif tile == player_seat_wind or tile == round_wind:
                        score *= 1.15
                    else:
                        score *= 0.8

                # 花色丟棄越多，該花色越不可能是等牌
                tile_suit = ''.join(filter(str.isalpha, tile))
                suit_discard_count = suit_count.get(tile_suit, 0)
                suit_multiplier = max(0.5, 1.0 - 0.035 * suit_discard_count)
                score *= suit_multiplier

                # 字牌剩兩張以上 → 增加危險
                is_honor_tile = tile.startswith("Feng") or tile.startswith("SanYuan")
                if is_honor_tile and remaining_tiles.get(tile, 0) >= 2:
                    score *= 1.25

                # 副露同花色 → 增加該花色危險度
                meld_suits = []
                for m in melds:
                    if isinstance(m, str):
                        meld_suits.append(''.join(filter(str.isalpha, m)))
                    elif isinstance(m, dict):
                        meld_suits += [''.join(filter(str.isalpha, t)) for t in m.get("tiles", [])]
                if tile_suit in meld_suits:
                    score *= 1.15

                # 數字位置調整
                if any(c.isdigit() for c in tile):
                    num = int(''.join(filter(str.isdigit, tile)))
                    if num in [4, 5, 6]:
                        score *= 1.25
                    elif num in [3, 7]:
                        score *= 1.2
                    elif num in [2, 8]:
                        score *= 1.1
                    elif num in [1, 9]:
                        score *= 1.0

                # 加入棄牌行為調整倍率
                wait_tiles[tile] = round(score, 2)

        wait_tiles = dict(sorted(wait_tiles.items(), key=lambda x: x[1], reverse=True))

        tenpai_info[f"p{pid}"] = {
            "is_riichi": is_riichi,
            "tenpai_probability":tenpai_prob,
            "wait_tiles": wait_tiles,
            "behavior_multiplier" :behavior_multiplier
        }

    return tenpai_info


def calculate_tile_value(tile, hand_tiles):
    from collections import Counter

    tile_counter = Counter(hand_tiles)
    same_tile_count = tile_counter[tile]

    value = 1.0
    
    if not any(c.isdigit() for c in tile):
        # 是字牌，只考慮對子和刻子
        if same_tile_count == 2:
            value *= 1.5  # 字牌對子略高
        elif same_tile_count >= 3:
            value *= 1.7  # 字牌刻子很強
        return round(value, 3)

    num = int(''.join(filter(str.isdigit, tile)))
    suit = ''.join(filter(str.isalpha, tile))

    # 提取同花色數字
    suit_tiles = sorted([
        int(''.join(filter(str.isdigit, t)))
        for t in hand_tiles
        if ''.join(filter(str.isalpha, t)) == suit
    ])



    # ===== 搭子潛力（單邊、兩邊） =====
    if (
        ((num + 2) in suit_tiles and (num + 1) not in suit_tiles) or 
        ((num - 2) in suit_tiles and (num - 1) not in suit_tiles)
    ):
        value *= 1.2 # 中洞
    elif (
        (num - 1 in suit_tiles and (num - 1) not in (1, 8)) or 
        (num + 1 in suit_tiles and (num + 1) not in (2, 9))
    ):
        value *= 1.25  # 兩邊搭子優

    elif (
        (num - 1 in suit_tiles and (num - 1) in (1, 8)) or 
        (num + 1 in suit_tiles and (num + 1) in (2, 9)) 
    ):
        value *= 1.15  # 單邊搭子
  
    # ===== 對子/刻子潛力 =====
    if same_tile_count == 2:
        value *= 1.25  # 對子略高一點
    elif same_tile_count >= 3:
        value *= 1.45 # 刻子

    # ===== 順子參與判定 =====
    for offset in (-2, -1, 0):
        if all((num + offset + i) in suit_tiles for i in range(3)):
            value *= 1.5  # 比原本略加重權重

    # 雙順子搭配
    if same_tile_count >= 2 and ((num - 1) in suit_tiles or (num + 1) in suit_tiles):
        value *= 1.25
        
    if value==1.0:
        value *=0.8
    return round(value, 3) 

        


# 危險度估算 + 最安全出牌
def estimate_overall_danger(self_hand, tenpai_info, total_tiles):
    def get_phase_weight(total_tiles):
        if total_tiles >= 40:
            return 0.8
        elif total_tiles >= 15:
            return 1.0
        else:
            return 1.2

    phase_weight = get_phase_weight(total_tiles)
    overall_danger = {}

    for tile in self_hand:
        total_risk = 0.0
        for pid in ["p2", "p3", "p4"]:
            if pid not in tenpai_info:
                continue

            base_risk = tenpai_info[pid]["wait_tiles"].get(tile, 0.0)
            total_risk += base_risk

        total_risk /= 3
        total_risk *= phase_weight

        tile_value = calculate_tile_value(tile, self_hand)

        total_risk *= tile_value

        danger_score = max(0.0, 10.0 - total_risk)
        overall_danger[tile] = round(danger_score, 3)

    
    overall_danger = dict(sorted(overall_danger.items(), key=lambda x: x[1], reverse=True))

    return {
        "overall_danger_scores": overall_danger,
    }


# 主程式
def main():
    file_path = "D:/mahjongproject/game_data.json"
    output_path = "D:/mahjongproject/analysis.json"
    data = read_game_data(file_path)

    all_tiles = {
        "Feng_E": 4, "Feng_N": 4, "Feng_S": 4, "Feng_W": 4,
        "SanYuan_G": 4, "SanYuan_R": 4, "SanYuan_W": 4,
        "Tiao1": 4, "Tiao2": 4, "Tiao3": 4, "Tiao4": 4, "Tiao5": 4, "Tiao6": 4, "Tiao7": 4, "Tiao8": 4, "Tiao9": 4,
        "Tong1": 4, "Tong2": 4, "Tong3": 4, "Tong4": 4, "Tong5": 4, "Tong6": 4, "Tong7": 4, "Tong8": 4, "Tong9": 4,
        "Wan1": 4, "Wan2": 4, "Wan3": 4, "Wan4": 4, "Wan5": 4, "Wan6": 4, "Wan7": 4, "Wan8": 4, "Wan9": 4
    }

    known_tiles = extract_known_tiles(data)
    remaining_tiles = calculate_remaining_tiles(all_tiles, known_tiles)
    
    raw_hand = data["players"]["1"].get("hand", [])
    self_hand = []
    for tile in raw_hand:
        if tile.endswith("_R") and tile[:-2][-1] == "5":
            # 赤寶牌 → 加入普通5號牌（如 Wan_5）
            self_hand.append(tile[:-2])
        else:
            self_hand.append(tile)
            
    tenpai_info = predict_tenpai(data, remaining_tiles)
    total_tiles = data.get("Total_tiles", [])
    danger_info = estimate_overall_danger(self_hand, tenpai_info, total_tiles)

    output_data = {
        "remaining_tiles": remaining_tiles,
        "tenpai_prediction": tenpai_info,
        "danger_estimation": {"danger_score": danger_info["overall_danger_scores"]},
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    while True:
        main()
        time.sleep(1)
