import numpy as np
import xml.etree.ElementTree as ET

tree = ET.parse(r'C:\Users\kamek\Desktop\project\roLabelImg-master\roLabelImg-master\demo\text.xml')
root = tree.getroot()

def get_rotated_rectangle_vertices(cx, cy, width, height, angle):
#旋轉角度轉為弧度
    theta = np.radians(angle)

#矩形四個頂點在未旋轉前的相對座標
    corners = np.array([
        [ width / 2,  height / 2],
        [-width / 2,  height / 2],
        [-width / 2, -height / 2],
        [ width / 2, -height / 2]
    ])

#旋轉矩陣
    rotation_matrix = np.array([
        [np.cos(theta), -np.sin(theta)],
        [np.sin(theta),  np.cos(theta)]
    ])

#旋轉後的頂點座標
    rotated_corners = np.dot(corners, rotation_matrix)

#平移至實際中心點
    rotated_corners += np.array([cx, cy])
    return rotated_corners

# 爆搜 XML 的標籤以找到 robndbox 的資料
for obj in root.findall('object'):
    robndbox = obj.find('robndbox')
    if robndbox is not None:
        # 提取數據
        cx = float(robndbox.find('cx').text)
        cy = float(robndbox.find('cy').text)
        width = float(robndbox.find('w').text)
        height = float(robndbox.find('h').text)
        angle = float(robndbox.find('angle').text)

        vertices = get_rotated_rectangle_vertices(cx, cy, width, height, angle)
        print(f"物件 {obj.find('name').text} 的頂點座標:")
        print(vertices)