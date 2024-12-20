from ultralytics import YOLO
import os
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

class Make_xml:
    # 創建 XML 文件的函數
    @staticmethod
    def create_voc_xml(filename, image_size, obbs, confs, classes, class_names, image_path):
        annotation = Element('annotation', verified="yes")

        folder = SubElement(annotation, 'folder')
        folder.text = os.path.basename(os.path.dirname(image_path))

        filename_elem = SubElement(annotation, 'filename')
        filename_elem.text = os.path.basename(image_path)

        path_elem = SubElement(annotation, 'path')
        path_elem.text = image_path

        source = SubElement(annotation, 'source')
        database = SubElement(source, 'database')
        database.text = 'Unknown'

        size = SubElement(annotation, 'size')
        width = SubElement(size, 'width')
        width.text = str(image_size[1])  # 寬度
        height = SubElement(size, 'height')
        height.text = str(image_size[0])  # 高度
        depth = SubElement(size, 'depth')
        depth.text = '3'

        segmented = SubElement(annotation, 'segmented')
        segmented.text = '0'

        for obb, conf, cls in zip(obbs, confs, classes):
            obj = SubElement(annotation, 'object')

            obj_type = SubElement(obj, 'type')
            obj_type.text = 'robndbox'  

            name = SubElement(obj, 'name')
            name.text = class_names[int(cls)]

            pose = SubElement(obj, 'pose')
            pose.text = 'Unspecified'

            truncated = SubElement(obj, 'truncated')
            truncated.text = '0'

            difficult = SubElement(obj, 'difficult')
            difficult.text = '0'

            robndbox = SubElement(obj, 'robndbox')

            center_x, center_y, width, height, theta = obb  # 提取旋轉框的 5 個參數
            
            cx_elem = SubElement(robndbox, 'cx')
            cx_elem.text = str(center_x)

            cy_elem = SubElement(robndbox, 'cy')
            cy_elem.text = str(center_y)

            w_elem = SubElement(robndbox, 'w')
            w_elem.text = str(width)

            h_elem = SubElement(robndbox, 'h')
            h_elem.text = str(height)

            angle_elem = SubElement(robndbox, 'angle')
            angle_elem.text = str(theta)

        xml_str = tostring(annotation, 'utf-8')
        parsed_str = parseString(xml_str)
        return parsed_str.toprettyxml(indent="  ")

    @staticmethod
    def summon_xml(temp_filepath):
        # 加載 YOLO 模型
        model = YOLO('yolov8n-obb.pt')
        filepath = os.path.abspath(temp_filepath)

        # 預測圖片
        results = model.predict(source=filepath, save=False)
        result = results[0]
        
        # 檢查是否有旋轉框數據
        if result.obb and result.obb.xywhr is not None:
            # 獲取圖像大小
            image_size = result.orig_shape  # (height, width)

            # 提取旋轉框數據
            obbs = result.obb.xywhr.cpu().numpy()
            confs = result.obb.conf.cpu().numpy()  
            classes = result.obb.cls.cpu().numpy() 
            class_names = model.names

            # 生成 XML
            xml_content = Make_xml.create_voc_xml(
                filename=os.path.splitext(os.path.basename(filepath))[0],
                image_size=image_size,
                obbs=obbs,
                confs=confs,
                classes=classes,
                class_names=class_names,
                image_path=filepath
            )

            # 保存 XML
            xml_filename = os.path.splitext(filepath)[0] + '.xml'
            with open(xml_filename, 'w') as f:
                f.write(xml_content)
        else:
            print(f"跳過圖片 {filepath}：未檢測到旋轉框數據！")

        print("所有圖片的 XML 文件生成完成！")