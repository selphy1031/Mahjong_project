import cv2
import mss
import numpy as np
from ultralytics import YOLO
import time
import json
import os

class MahjongDetection:
    def __init__(self, mid_model_path, tiles_model_path, json_file_path):
        """初始化 YOLO 模型"""
        self.round_wind = "Feng_E"
        self.mid_model = YOLO(mid_model_path)  # 行動指示燈模型
        self.tiles_model = YOLO(tiles_model_path)  # 麻將牌偵測模型
        self.players_winds = {} #玩家風位儲存
        self.previous_step = None  # 記錄上一位玩家
        self.json_file_path = json_file_path #json檔儲存路
        self.melds_length = 0 #副露長度
        self.melds_length_hand = 0 #副露長度，專門計算手牌用
        self.banker_history = []
        self.initial_banker = None #紀錄最初的莊家
        self.current_banker = None
        self.no_banker_count = 0
        self.Total_tiles = 70
        self.init_json() #json檔初始化

    def init_json(self):
        """初始化 JSON 檔案，如果存在則刪除舊檔案，創建新的空白檔案"""
        try:
            # 如果 JSON 檔案存在，先刪除
            if os.path.exists(self.json_file_path):
                os.remove(self.json_file_path)
                print(f"舊的 JSON 檔案已刪除：{self.json_file_path}")

            os.makedirs(os.path.dirname(self.json_file_path), exist_ok=True)

            # 創建新的空白 JSON 檔案
            data = {
                "field_wind": self.round_wind,
                "Total_tiles": self.Total_tiles,
                "Banker": None,  # 初始無莊家
                "Step": None,
                "dora": [],
                "players": {
                    "1": {"Wind":[], "Riichi":[], "hand": [], "discarded": [], "melds": []},
                    "2": {"Wind":[], "Riichi":[], "discarded": [], "melds": []},
                    "3": {"Wind":[], "Riichi":[], "discarded": [], "melds": []},
                    "4": {"Wind":[], "Riichi":[], "discarded": [], "melds": []}
                }
            }

            # 寫入新的 JSON 檔案
            with open(self.json_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"已創建新的 JSON 檔案：{self.json_file_path}")

        except Exception as e:
            print(f"初始化 JSON 時發生錯誤: {e}")
            
    def letterbox(self, img, new_shape=(480, 540)):
        """保持圖像大小不變，僅填充多餘的空白區域"""
        shape = img.shape[:2]  # 取得原圖大小 (height, width)
        
        # 計算填充區域 (dw: 左右填充量, dh: 上下填充量)
        dw, dh = new_shape[1] - shape[1], new_shape[0] - shape[0]  # 寬度差與高度差

        # 如果寬度或高度小於目標大小，則均勻分配填充
        dw, dh = dw // 2, dh // 2
        right, bottom = new_shape[1] - shape[1] - dw, new_shape[0] - shape[0] - dh

        # 如果填充量為負，設置為0，防止錯誤
        dw, dh = max(0, dw), max(0, dh)
        right, bottom = max(0, right), max(0, bottom)

        # 使用 cv2.copyMakeBorder 來填充空白區域
        img_padded = cv2.copyMakeBorder(img, dh, bottom, dw, right, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        return img_padded
        
    def compute_dst_size(self, src_points):
        """根據平行四邊形的角點計算目標大小 (寬, 高)"""
        p1, p2, p3, p4 = np.array(src_points)
        
        # 計算上邊和下邊的寬度
        width_top = np.linalg.norm(p2 - p1)   # 上邊長度
        width_bottom = np.linalg.norm(p4 - p3)  # 下邊長度
        width = int(max(width_top, width_bottom))  # 取較大值，避免扭曲

        # 計算左邊和右邊的高度
        height_left = np.linalg.norm(p3 - p1)   # 左邊長度
        height_right = np.linalg.norm(p4 - p2)  # 右邊長度
        height = int(max(height_left, height_right))  # 取較大值，避免扭曲

        return (width, height)

    def perspective_crop(self, img, src_points):
        """使用透視變換擷取平行四邊形區域，並自動轉換為固定大小的矩形"""
        dst_size = self.compute_dst_size(src_points)  # 計算目標大小
        
        dst_points = np.float32([
            [0, 0], 
            [dst_size[0], 0], 
            [0, dst_size[1]], 
            [dst_size[0], dst_size[1]]
        ])
        
        # 計算透視變換矩陣
        matrix = cv2.getPerspectiveTransform(np.float32(src_points), dst_points)
        
        # 透視變換
        warped = cv2.warpPerspective(img, matrix, dst_size)
        #warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        return warped
    
    def crop_regions(self, frame):
        """裁剪所有區域"""
        
        size_mid = (70, 250)
        size_tiles = (540, 480)
        
        Regions_Mid = {
            'Player1_Mid': {'region': frame[490:535, 790:1050].copy(), 'description': '1'},
            'Player2_Mid': {'region': frame[360:540, 1065:1130].copy(), 'description': '2'},
            'Player3_Mid': {'region': frame[315:355, 870:1115].copy(), 'description': '3'},
            'Player4_Mid': {'region': frame[315:480, 805:860].copy(), 'description': '4'}
        }

        # 旋轉
        Regions_Mid['Player2_Mid']['region'] = cv2.rotate(Regions_Mid['Player2_Mid']['region'], cv2.ROTATE_90_CLOCKWISE)
        Regions_Mid['Player3_Mid']['region'] = cv2.rotate(Regions_Mid['Player3_Mid']['region'], cv2.ROTATE_180)
        Regions_Mid['Player4_Mid']['region'] = cv2.rotate(Regions_Mid['Player4_Mid']['region'], cv2.ROTATE_90_COUNTERCLOCKWISE)

        for key in Regions_Mid:
            Regions_Mid[key]['region'] = self.letterbox(Regions_Mid[key]['region'], size_mid)
            
        Regions_Tiles = {
            1: {
                'player1_hand': {'region': frame[900:1070, 200:1575-self.melds_length_hand*80].copy(), 'description': '1_hand'},
                'player1_discard': {'region': frame[540:770, 750:1150].copy(), 'description': '1_discard'},
                'player1_melds': {'region': frame[940:1050, 1585-self.melds_length*80:1830].copy(), 'description': '1_melds'},
            },
            2: {
                'player2_discard': {'region': frame[270:550, 1130:1410].copy(), 'description': '2_discard'},
                'player2_melds': {
                    #前兩個不動。最一開始四個為一組 x越來越大 y越來越大
                    'src_points': [(1465, 35), (1570, 35), (1510+self.melds_length*13, 180+self.melds_length*40), (1615+self.melds_length*13, 180+self.melds_length*40)],
                    'description': '2_melds'
                },
            },
            3: {
                'player3_discard': {'region': frame[110:310, 770:1140].copy(), 'description': '3_discard'},
                'player3_melds':{'region': frame[30:95, 385:605+self.melds_length*60].copy(), 'description': '3_melds'},
            },
            4: {
                'player4_discard': {'region': frame[270:570, 520:780].copy(), 'description': '4_discard'},
                'player4_melds': {
                    #後兩個不動。最一開始四個為一組 x越來越大 y越來越小
                    'src_points': [(135+self.melds_length*15, 690-self.melds_length*45), (290+self.melds_length*15, 690-self.melds_length*45), (45, 975), (200, 975)],
                    'description': '4_melds'
                },
            }
        }

        for player_key in Regions_Tiles:
            for key in Regions_Tiles[player_key]:
                region_data = Regions_Tiles[player_key][key]
                
                if player_key in [2, 4] and 'src_points' in region_data:  # 如果是 melds 區域，需要進行透視變換
                    # 取得透視變換需要的 src_points
                    src_points = region_data['src_points']
                    
                    # 透視變換
                    region = self.perspective_crop(frame, src_points)
                    
                    # 進行 letterbox 操作
                    region = self.letterbox(region, size_tiles)
                    
                    # 更新結果
                    region_data['region'] = region
                else:
                    # 其他區域只需要進行 letterbox
                    region_data['region'] = self.letterbox(region_data['region'], size_tiles)

                
        Regions_Tiles_Dora = {
            'dora_indicator': {'region': frame[40:130, 25:310].copy(), 'description': 'dora'}
        }

        Regions_Tiles_Dora['dora_indicator']['region'] = self.letterbox(Regions_Tiles_Dora['dora_indicator']['region'], size_tiles)
        return Regions_Mid, Regions_Tiles, Regions_Tiles_Dora
    
    def detect_mid(self, frame):
        """偵測莊家、未立直標記與行動指示燈"""
        Regions_Mid, _, _ = self.crop_regions(frame)
        banker = None         # 儲存莊家的偵測結果
        riichi = {}     # 儲存未立直的偵測結果
        step = None  # 儲存行動玩家的編號
        
        for player_key, player_info in Regions_Mid.items():
            player_num = int(player_info['description'])  # 玩家編號
            results = self.mid_model(player_info['region'])
            
            riichi[str(player_num)] = "true"

            # 遍歷所有偵測到的物體
            for result in results:
                for box in result.boxes.data:
                    x1, y1, x2, y2, conf, cls = box
                    class_name = self.mid_model.model.names[int(cls)]
                    
                    if conf > 0.5:  # 設定信心值閾值
                        # 偵測莊家
                        if class_name == 'Banker':
                            banker = player_num
                        # 偵測未立直
                        elif class_name == 'UnRiichi':
                            riichi[str(player_num)] = "false"
                        # 偵測行動指示燈
                        elif class_name == 'step':
                            step = player_num

        return banker, riichi, step
    
    def detect_tiles(self, frame, step):
        """偵測對應的 Regions_Tiles 並進行麻將牌辨識"""
        _, Regions_Tiles, _ = self.crop_regions(frame)

        if step not in Regions_Tiles:
            return {}

        regions = Regions_Tiles[step]
        detected_tiles = {}

        for key, value in regions.items():
            region = value['region']
            results = self.tiles_model(region)

            tile_list = []
            for result in results:
                for box in result.boxes.data:
                    x1, y1, x2, y2, conf, cls = box
                    class_name = self.tiles_model.model.names[int(cls)]
                    if conf > 0.5:
                        tile_list.append(class_name)

            detected_tiles[key] = tile_list

        return detected_tiles

    def detect_dora(self, frame):
        """偵測寶牌區域"""
        _, _, Regions_Tiles_Dora = self.crop_regions(frame)
        region = Regions_Tiles_Dora['dora_indicator']['region']
        results = self.tiles_model(region)

        dora_tiles = []
        for result in results:
            for box in result.boxes.data:
                x1, y1, x2, y2, conf, cls = box
                class_name = self.tiles_model.model.names[int(cls)]
                if conf > 0.5:
                    dora_tiles.append(class_name)

        return dora_tiles
    
    def determine_winds(self, banker):
        """根据庄家描述确定所有玩家的风位"""
        wind_order = ["Feng_E", "Feng_S", "Feng_W", "Feng_N"]

        # 将庄家的 description 转换为整数
        dealer_index = banker - 1  # '1' -> 0, '2' -> 1, '3' -> 2, '4' -> 3

        # 计算所有玩家风位
        self.players_winds = {str(i + 1): wind_order[(i - dealer_index) % 4] for i in range(4)}
        
    def update_banker(self, banker): #未測試
        """更新莊家資訊並檢查是否需要變更場風"""
        
        if banker:
            self.no_banker_count = 0
            if self.initial_banker is None:
                self.initial_banker = banker  # 記錄最初的莊家
            
            if banker != self.current_banker:
                self.banker_history.append(banker)
                self.current_banker = banker
            
            # **如果莊家輪回最初的玩家，則改變場風**
            if len(set(self.banker_history)) >= 4 and self.current_banker == self.initial_banker:
                self.change_round_wind()
                self.banker_history.clear()
                self.banker_history.append(self.current_banker)
        else:
            self.no_banker_count += 1  # **未偵測到莊家，累積計數**
            print(f"未偵測到莊家 {self.no_banker_count} 次")

            # **4 次沒偵測到莊家 → 進入新的一局**
            if self.no_banker_count >= 4:
                self.init_json()

            # **20 次沒偵測到莊家 → 進入新的一場**
            if self.no_banker_count >= 20:
                self.__init__()

        return self.banker_history
    
    def change_round_wind(self): #未測試
        """改變場風"""
        wind_order = ["東", "南", "西", "北"]  # 假設有西風戰
        current_index = wind_order.index(self.round_wind)
        
        if current_index < len(wind_order) - 1:
            self.round_wind = wind_order[current_index + 1]
            
    def update_json(self, frame):
        """更新 JSON 檔案中的部分資料，確保不覆蓋整個檔案，只修改必要的部分"""
        try:
            
            banker, riichi, step = self.detect_mid(frame)
            
            self.update_banker(banker)
            
            if step is None:
                print("無法獲得有效的step，跳過更新")
                return
            
            self.determine_winds(banker)
            
            # 偵測資料
            detected_tiles = self.detect_tiles(frame, step)  # 偵測當前玩家的牌
            dora_tiles = self.detect_dora(frame)  # 偵測寶牌
        
            # 讀取現有 JSON 檔案
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if self.previous_step and self.previous_step != step:
                print(f"偵測上一位玩家 {self.previous_step} 的區域")
                
                prev_key = str(self.previous_step)
                
                detected_tiles_prev = self.detect_tiles(frame, self.previous_step)
                if prev_key == "1":
                    data["players"][prev_key]["hand"] = detected_tiles_prev.get("player1_hand", [])
                    
                data["players"][prev_key]["Wind"] = self.players_winds.get(prev_key, [])
                data["players"][prev_key]["Riichi"] = riichi.get(prev_key, [])
                new_discarded = detected_tiles_prev.get(f"player{prev_key}_discard", [])
                prev_discarded = data["players"][prev_key]["discarded"]

                # **比較新舊棄牌數量，選擇較多的那個**
                data["players"][prev_key]["discarded"] = new_discarded if len(new_discarded) >= len(prev_discarded) else prev_discarded
                data["players"][prev_key]["melds"] = detected_tiles_prev.get(f"player{prev_key}_melds", [])

                data["dora"] = dora_tiles
                
            # 更新當前行動玩家的資料
            player_key = str(step)
            data["Step"] = step
            
            if player_key == "1":
                data["players"][player_key]["hand"] = detected_tiles.get("player1_hand", [])
                self.melds_length_hand = len(data["players"][player_key]["melds"])
            new_discarded = detected_tiles.get(f"player{player_key}_discard", [])
            prev_discarded = data["players"][player_key]["discarded"]

            self.melds_length = len(data["players"][player_key]["melds"])
            # **比較新舊棄牌數量，選擇較多的那個**
            data["players"][player_key]["discarded"] = new_discarded if len(new_discarded) >= len(prev_discarded) else prev_discarded

            data["Banker"] = banker
            
            self.Total_tiles = 70 - sum(len(data["players"][str(player_id)]["discarded"]) for player_id in range(1, 5))
            data["Total_tiles"] = self.Total_tiles
            # 將更新後的資料寫回 JSON 檔案
            with open(self.json_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                          
            self.previous_step = step
            
            print(f"JSON 檔案已更新：{self.json_file_path}")
            
        
        except Exception as e:
            print(f"更新 JSON 時發生錯誤: {e}")

def capture_screen(region=None):
    """使用 mss 庫捕獲屏幕畫面"""
    with mss.mss() as sct:
        monitor = region if region else sct.monitors[1]
        img = sct.grab(monitor)
        frame = cv2.cvtColor(np.array(img), cv2.COLOR_BGRA2BGR)
        return frame

if __name__ == "__main__":
    detector = MahjongDetection(
        mid_model_path="D:/mahjongproject/Mid_Best.pt",
        tiles_model_path="D:/mahjongproject/Tiles_Best.pt",
        json_file_path="D:/mahjongproject/game_data.json"
    )
    
    last_detect_time = time.time()
    detection_interval = 0.5

    while True:
        frame = capture_screen(region={"top": 0, "left": 0, "width": 1920, "height": 1080})
        current_time = time.time()

        if current_time - last_detect_time >= detection_interval:
            detector.update_json(frame)
            
            last_detect_time = current_time

        if cv2.waitKey(1) == ord("q"):
            print("❌ 程式結束...")
            break

    cv2.destroyAllWindows()