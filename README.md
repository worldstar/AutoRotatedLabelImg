# RotatedAutoLabelImg

RotatedAutoLabelImg 是一款圖形化的圖像標註工具，能自動化標註。這是 "roLabelImg" 的重寫版本，並且加入了 YOLOv8 OBB。

原始版本 "roLabelImg" 可以在[這裡](https://github.com/cgvict/roLabelImg)找到。

"YOLOv8 OBB" 可以在[這裡](https://github.com/orgs/ultralytics/discussions/7472)找到。

此工具使用 Python 編寫，並採用了 Qt 作為其圖形界面框架。

### 功能

#### 自動標註模式

| 功能           | 描述                                       |
|----------------|-------------------------------------------|
| 標註並下一張   | 自動標註當前圖片並切換到下一張             |
| 標註這張       | 自動標註當前圖片                          |
| 自動標註       | 自動標註資料夾內所有圖片                  |

### 演示

![演示圖](https://github.com/worldstar/RotatedAutoLabelImg/blob/master/demo/redemo1.png)

![演示 GIF](https://raw.githubusercontent.com/cgvict/roLabelImg/master/demo/demo_v2.5.gif)

[觀看 YouTube 上的演示](https://youtu.be/7D5lvol_QRA)

標註將以 XML 文件格式保存，類似於 [ImageNet](http://www.image-net.org/) 使用的 PASCAL VOC 格式。

### XML 格式範例

```xml
<annotation verified="yes">
  <folder>hsrc</folder>
  <filename>100000001</filename>
  <path>/Users/haoyou/Library/Mobile Documents/com~apple~CloudDocs/OneDrive/hsrc/100000001.bmp</path>
  <source>
    <database>Unknown</database>
  </source>
  <size>
    <width>1166</width>
    <height>753</height>
    <depth>3</depth>
  </size>
  <segmented>0</segmented>
  <object>
    <type>bndbox</type>
    <name>ship</name>
    <pose>Unspecified</pose>
    <truncated>0</truncated>
    <difficult>0</difficult>
    <bndbox>
      <xmin>178</xmin>
      <ymin>246</ymin>
      <xmax>974</xmax>
      <ymax>504</ymax>
    </bndbox>
  </object>
  <object>
    <type>robndbox</type>
    <name>ship</name>
    <pose>Unspecified</pose>
    <truncated>0</truncated>
    <difficult>0</difficult>
    <robndbox>
      <cx>580.7887</cx>
      <cy>343.2913</cy>
      <w>775.0449</w>
      <h>170.2159</h>
      <angle>2.889813</angle>
    </robndbox>
  </object>
</annotation>
```

### 安裝

#### 下載原版 `labelImg` 的預建二進制文件

- [Windows & Linux](http://tzutalin.github.io/labelImg/)
- OS X: 暫無預建二進制文件，需從源碼構建。

#### 從源碼構建

##### Ubuntu Linux

```bash
sudo apt-get install pyqt4-dev-tools
sudo pip install lxml
make all
./roLabelImg.py
./roLabelImg.py [IMAGE_PATH] [PRE-DEFINED CLASS FILE]
```

##### OS X

```bash
brew install qt qt4
brew install libxml2
make all
./roLabelImg.py
./roLabelImg.py [IMAGE_PATH] [PRE-DEFINED CLASS FILE]
```

##### Windows

1. 下載並安裝 [Python 2.6 或更高版本](https://www.python.org/downloads/windows/)。
2. 安裝 [PyQt4](https://www.riverbankcomputing.com/software/pyqt/download) 和 [lxml](http://lxml.de/installation.html)。
3. 打開命令行並導航到 `roLabelImg` 目錄。

```bash
pyrcc4 -o resources.py resources.qrc
python roLabelImg.py
python roLabelImg.py [IMAGE_PATH] [PRE-DEFINED CLASS FILE]
```

#### 使用 Docker

```bash
docker pull tzutalin/py2qt4

docker run -it \
--user $(id -u) \
-e DISPLAY=unix$DISPLAY \
--workdir=$(pwd) \
--volume="/home/$USER:/home/$USER" \
--volume="/etc/group:/etc/group:ro" \
--volume="/etc/passwd:/etc/passwd:ro" \
--volume="/etc/shadow:/etc/shadow:ro" \
--volume="/etc/sudoers.d:/etc/sudoers.d:ro" \
-v /tmp/.X11-unix:/tmp/.X11-unix \
tzutalin/py2qt4
```

### 使用方法

#### 步驟

**手動標註**

1. 按照上述指引構建並啟動。
2. 點擊 `菜單/文件` 中的 `更改預設保存標註文件夾`。
3. 點擊 `打開資料夾`。
4. 點擊 `創建矩形框`。
5. 點擊並釋放滑鼠左鍵，選擇一個區域進行標註。
6. 使用滑鼠右鍵拖動、複製或移動矩形框。

**自動標註**

1. 按照上述指引構建並啟動。
2. 點擊 `菜單/文件` 中的 `更改預設保存標註文件夾`。
3. 點擊 `標註並下一張`、`標註這張` 或 `自動標註`。
4. 等待生成完成。
5. 使用滑鼠左鍵移動矩形框，右鍵旋轉或複製矩形框。

標註將保存到您指定的文件夾。

#### 快捷鍵

| 快捷鍵       | 功能                                       |
|--------------|-------------------------------------------|
| Ctrl + u     | 從目錄加載所有圖片                        |
| Ctrl + r     | 更改預設標註目標文件夾                    |
| Ctrl + s     | 保存                                      |
| Ctrl + d     | 複製當前標籤和矩形框                      |
| 空格         | 將當前圖片標記為已驗證                    |
| w            | 創建矩形框                                |
| e            | 創建旋轉矩形框                            |
| d            | 下一張圖片                                |
| a            | 上一張圖片                                |
| r            | 顯示/隱藏旋轉矩形框                       |
| n            | 顯示/隱藏普通矩形框                       |
| del          | 刪除選中的矩形框                          |
| Ctrl++       | 放大                                      |
| Ctrl--       | 縮小                                      |
| ↑→↓←       | 使用鍵盤箭頭移動選中的矩形框               |
| zxcv         | 使用鍵盤旋轉選中的矩形框                  |

### 如何貢獻

提交拉取請求。

### 授權

[MIT 授權](https://github.com/cgvict/roLabelImg/blob/master/LICENSE)

### 相關

1. [ImageNet 工具](https://github.com/tzutalin/ImageNet_Utils): 用於下載圖片、創建機器學習標籤文本等。
2. [Docker hub](https://hub.docker.com/r/tzutalin/py2qt4) 用於運行工具。
