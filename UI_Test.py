from PyQt5 import QtCore, QtGui, QtWidgets
import sys
import json
import os
import subprocess

process = None
process1 = None

class TransparentOverlay(QtWidgets.QWidget):    

    def __init__(self):
        super().__init__()
        self.analysis_timer = QtCore.QTimer()
        self.chances = {}
        self.filtered_tiles = []
        self.init_ui()
        self.init_timer()

    def init_ui(self):
        self.setGeometry(0, 0, 1920, 1080)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        # 建立聽牌機率顯示的 Label
        self.tenpai_labels = {}
        self.image_tile_img = {}
        positions = {"p2": (1725, 460), "p3": (1180, 30), "p4": (40, 450)}  # 可調整位置

        for player, (x, y) in positions.items():
            self.tenpai_labels[player] = QtWidgets.QLabel(f"{player} 聽牌機率: 000%", self)
            self.tenpai_labels[player].setStyleSheet("color: white; font-size: 20px;")
            self.tenpai_labels[player].move(x, y)
            self.tenpai_labels[player].hide()
            
            self.image_tile_img[player] = []  # 先初始化為空 list
            
            for i in range(50):
                if i%6 ==0 and i !=0:
                    x=x-180
                    y += 50
                img_label = QtWidgets.QLabel(self)
                img_label.setGeometry(x + i * 30, y +30 , 25, 40)
                img_label.setStyleSheet("background: transparent;")
                self.image_tile_img[player].append(img_label)  # 加進 list

        # 顯示推薦打牌文字 Label
        self.recommend_label = QtWidgets.QLabel("推薦打牌：", self)
        self.recommend_label.setStyleSheet("color: white; font-size: 20px;")
        self.recommend_label.move(390, 620)
        self.recommend_label.hide()

        self.recommend_tile_imgs = []  # 建立 list

        for i in range(50):
            label = QtWidgets.QLabel(self)
            label.setGeometry(390 + i * 30, 650, 25, 40)  # 可微調位置與大小
            label.setStyleSheet("background: transparent;")
            label.hide()
            self.recommend_tile_imgs.append(label)  # 加入 list


        # 控制按鈕區塊
        self.button_settings = QtWidgets.QPushButton("設定", self)
        self.button_start = QtWidgets.QPushButton("開始讀取", self)
        self.button_stop = QtWidgets.QPushButton("停止讀取", self)
        self.button_close = QtWidgets.QPushButton("關閉", self)

        for btn in [self.button_settings, self.button_start, self.button_stop, self.button_close]:
            btn.setStyleSheet("background-color: rgba(255,255,255,180); font-size: 14px;")

        self.button_settings.move(1520, 10)
        self.button_start.move(1620, 10)
        self.button_stop.move(1720, 10)
        self.button_close.move(1820, 10)

        self.button_settings.clicked.connect(self.open_settings)
        self.button_start.clicked.connect(self.start_timer)
        self.button_stop.clicked.connect(self.stop_timer)
        self.button_close.clicked.connect(QtWidgets.QApplication.quit)
        
        #背景板
        self.background_widget = QtWidgets.QWidget(self)
        self.background_widget.setGeometry(1285, 10, 190, 100)  # 背景板大小與位置可以根據需要調整
        self.background_widget.setStyleSheet("background-color: rgba(255,255,255,180); border-radius: 10px;")
        self.background_widget.hide()
        
        #危險值-文字
        self.slider_danger_label_text = QtWidgets.QLabel("危險值：", self)
        self.slider_danger_label_text.setGeometry(1280, 15, 100, 20)  # 標籤放在滑桿左邊
        self.slider_danger_label_text.setStyleSheet("font-size: 14px;")
        self.slider_danger_label_text.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_danger_label_text.hide()
        
        #危險值-滑桿
        self.slider_danger = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider_danger.setGeometry(1360, 15, 80, 20)  # 在設定按鈕左邊
        self.slider_danger.setMinimum(0)
        self.slider_danger.setMaximum(10)
        self.slider_danger.setValue(0)
        self.slider_danger.hide()
        
        #危險值-數字
        self.slider_danger_label = QtWidgets.QLabel(str(self.slider_danger.value()), self)
        self.slider_danger_label.setGeometry(1435, 15, 50, 20)  # 放在滑桿右邊
        self.slider_danger_label.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_danger_label.setStyleSheet("font-size: 14px;")
        self.slider_danger_label.hide()
        
        #聽牌機率-文字
        self.slider_chance_label_text = QtWidgets.QLabel("聽牌機率：", self)
        self.slider_chance_label_text.setGeometry(1275, 50, 100, 20)  
        self.slider_chance_label_text.setStyleSheet("font-size: 14px;")
        self.slider_chance_label_text.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_chance_label_text.hide()
        
        #聽牌機率-滑桿
        self.slider_chance = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider_chance.setGeometry(1360, 50, 80, 20)  # 在設定按鈕左邊
        self.slider_chance.setMinimum(0)
        self.slider_chance.setMaximum(100)
        self.slider_chance.setValue(0)
        self.slider_chance.hide()
        
        #聽牌機率-數字
        self.slider_chance_label = QtWidgets.QLabel(str(self.slider_chance.value()), self)
        self.slider_chance_label.setGeometry(1435, 45, 50, 30)  
        self.slider_chance_label.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_chance_label.setStyleSheet("font-size: 12px;")
        self.slider_chance_label.hide()
        
        #推薦打牌-文字
        self.slider_recommend_label_text = QtWidgets.QLabel("推薦打牌：", self)
        self.slider_recommend_label_text.setGeometry(1275, 85, 100, 20)  
        self.slider_recommend_label_text.setStyleSheet("font-size: 14px;")
        self.slider_recommend_label_text.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_recommend_label_text.hide()
        
        #推薦打牌-滑桿
        self.slider_recommend = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider_recommend.setGeometry(1360, 85, 80, 20)  # 在設定按鈕左邊
        self.slider_recommend.setMinimum(0)
        self.slider_recommend.setMaximum(10)
        self.slider_recommend.setValue(0)
        self.slider_recommend.hide()
        
        #推薦打牌-數字
        self.slider_recommend_label = QtWidgets.QLabel(str(self.slider_recommend.value()), self)
        self.slider_recommend_label.setGeometry(1435, 80, 50, 30)  
        self.slider_recommend_label.setAlignment(QtCore.Qt.AlignCenter)
        self.slider_recommend_label.setStyleSheet("font-size: 12px;")
        self.slider_recommend_label.hide()
        
        self.slider_danger.valueChanged.connect(self.update_slider_danger_label)
        self.slider_chance.valueChanged.connect(self.update_slider_chance_label)
        self.slider_recommend.valueChanged.connect(self.update_slider_recommend_label)
        
    def open_settings(self):
        if self.slider_danger.isVisible():
            self.slider_danger.hide()
            self.slider_danger_label.hide()
            self.slider_danger_label_text.hide()
            self.slider_chance.hide()
            self.slider_chance_label.hide()
            self.slider_chance_label_text.hide()
            self.slider_recommend.hide()
            self.slider_recommend_label.hide()
            self.slider_recommend_label_text.hide()
            self.background_widget.hide()
        else:
            self.slider_danger.show()
            self.slider_danger_label.show()
            self.slider_danger_label_text.show()
            self.slider_chance.show()
            self.slider_chance_label.show()
            self.slider_chance_label_text.show()
            self.slider_recommend.show()
            self.slider_recommend_label.show()
            self.slider_recommend_label_text.show()
            self.background_widget.show()
            
    def update_slider_danger_label(self, value: int) -> None:
        self.slider_danger_label.setText(str(value))
        
    def update_slider_chance_label(self, value: int) -> None:
        self.slider_chance_label.setText(str(value))
        
    def update_slider_recommend_label(self, value: int) -> None:
        self.slider_recommend_label.setText(str(value))

    def init_timer(self):
        self.analysis_timer.setInterval(1000)
        self.analysis_timer.timeout.connect(self.load_analysis_data)

    def start_timer(self):
        self.analysis_timer.start()
        self.recommend_label.show()
        start_detection()
        for label in self.recommend_tile_imgs:
            label.show()
        for label in self.tenpai_labels.values():
            label.show()
        for player_labels in self.image_tile_img.values():
            for img_label in player_labels:
                img_label.show()

    def stop_timer(self):
        self.analysis_timer.stop()
        self.recommend_label.hide()
        stop_detection()
            
        for label in self.recommend_tile_imgs:
            label.hide()
        for label in self.tenpai_labels.values():
            label.hide()
        for player_labels in self.image_tile_img.values():
            for img_label in player_labels:
                img_label.hide()

               
    def load_analysis_data(self):
        try:
            with open(r"D:/mahjongproject/analysis.json", "r", encoding="utf-8") as file:
                data = json.load(file)

                self.chances = {
                    player: data.get("tenpai_prediction", {}).get(player, {}).get("tenpai_probability", 0)
                    for player in ["p2", "p3", "p4"]
                }

                # 顯示推薦打牌文字與圖片
                safe_discards = data.get("danger_estimation", {}).get("danger_score", {})
                self.recommend_label.setText("推薦打牌：")
                
                safe_tiles = [
                            tile for tile, danger in sorted(safe_discards.items(), key=lambda x: -x[1])
                            if danger >= self.slider_recommend.value()
                        ]
                for i in range(len(safe_tiles)):
                    tile_name = safe_tiles[i]
                    tile_path = os.path.join("D:/mahjongproject/MahJongPicture", f"{tile_name}.png")
                    if os.path.exists(tile_path):
                            pixmap = QtGui.QPixmap(tile_path).scaled(25, 40, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                            self.recommend_tile_imgs[i].setPixmap(pixmap)
                            self.recommend_tile_imgs[i].show()
                    else:
                            self.recommend_tile_imgs[i].clear()
                            self.recommend_tile_imgs[i].hide()
                    # 清除多餘的圖片
                for i in range(len(safe_tiles), len(self.recommend_tile_imgs)):
                    self.recommend_tile_imgs[i].clear()
                    self.recommend_tile_imgs[i].hide()
                
                # 顯示每位對手的聽牌機率與等牌圖片
                for player in ["p2", "p3", "p4"]:
                    chance = self.chances.get(player, 0)
                    self.tenpai_labels[player].setText(f"{player} 聽牌機率: {chance}%")
                    self.tenpai_labels[player].show()

                    player_data = data.get("tenpai_prediction", {}).get(player, {})
                    
                    # 取得 danger_tiles 字典 {tile_name: danger_value}
                    danger_dict = player_data.get("wait_tiles", {})

                    # 檢查該玩家的 chance 是否大於或等於設定的 slider_chance
                    if chance >= self.slider_chance.value():  # 使用 slider_chance 設定值
                        self.filtered_tiles = [
                            tile for tile, danger in sorted(danger_dict.items(), key=lambda x: -x[1])
                            if danger >= self.slider_danger.value()
                        ]
                        # 顯示危險牌
                        for i in range(len(self.filtered_tiles)):
                            tile_name = self.filtered_tiles[i]
                            tile_path = os.path.join("D:/mahjongproject/MahJongPicture", f"{tile_name}.png")
                            if os.path.exists(tile_path):
                                pixmap = QtGui.QPixmap(tile_path).scaled(25, 40, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                                self.image_tile_img[player][i].setPixmap(pixmap)
                                self.image_tile_img[player][i].show()
                            else:
                                self.image_tile_img[player][i].clear()
                                self.image_tile_img[player][i].hide()

                        # 清除多餘的圖片
                        for i in range(len(self.filtered_tiles), len(self.image_tile_img[player])):
                            self.image_tile_img[player][i].clear()
                            self.image_tile_img[player][i].hide()
                    else:
                        # 若聽牌機率低於閾值，則不顯示危險牌
                        for i in range(len(self.image_tile_img[player])):
                            self.image_tile_img[player][i].clear()
                            self.image_tile_img[player][i].hide()
        except Exception as e:
            print("讀取 analysis.json 失敗:", e)
            for player in ["p2", "p3", "p4"]:
                self.tenpai_labels[player].setText(f"{player} 資料讀取失敗")
                for label in self.image_tile_img[player]:
                    label.clear()
            self.recommend_tile_imgs.clear()


def start_detection():
    global process,process1
    process = subprocess.Popen(["python", r"D:/mahjongproject/FinalDetection.py"])
    process1 = subprocess.Popen(["python", r"D:/mahjongproject/analysis_version2.py"])

def stop_detection():
    global process
    process.terminate() # 終止辨識程式
    process1.terminate()
    
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    overlay = TransparentOverlay()
    overlay.show()
    sys.exit(app.exec_())


