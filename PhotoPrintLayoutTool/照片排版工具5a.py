import sys
import math
import json
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QComboBox, 
                            QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QGroupBox, QFileDialog, QLineEdit, QMessageBox,
                            QRadioButton, QButtonGroup, QScrollArea, QDialog,
                            QDialogButtonBox, QFormLayout)
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush, QFont
from PyQt5.QtCore import Qt, QSize, QSettings

class SizeManager:
    """尺寸管理器，处理尺寸数据的加载和保存"""
    DEFAULT_PHOTO_SIZES = [
        {"name": "1寸", "width": 2.5, "height": 3.5},
        {"name": "2寸", "width": 3.5, "height": 4.9},
        {"name": "小1寸", "width": 2.2, "height": 3.2},
        {"name": "大1寸", "width": 3.3, "height": 4.8},
        {"name": "5寸", "width": 8.9, "height": 12.7},
        {"name": "签证照片", "width": 3.5, "height": 4.5},
        {"name": "身份证照片", "width": 3.5, "height": 5.3},
        {"name": "护照照片", "width": 3.5, "height": 4.5},
    ]
    
    DEFAULT_CANVAS_SIZES = [
        {"name": "6寸(4R)", "width": 10.2, "height": 15.2},
        {"name": "5寸(3R)", "width": 8.9, "height": 12.7},
        {"name": "7寸(5R)", "width": 12.7, "height": 17.8},
        {"name": "A4", "width": 21.0, "height": 29.7},
        {"name": "A5", "width": 14.8, "height": 21.0},
        {"name": "A6", "width": 10.5, "height": 14.8},
    ]
    
    def __init__(self):
        self.settings = QSettings("PhotoLayoutTool", "SizeConfig")
        self.photo_sizes = self.load_sizes("photo_sizes", self.DEFAULT_PHOTO_SIZES)
        self.canvas_sizes = self.load_sizes("canvas_sizes", self.DEFAULT_CANVAS_SIZES)
    
    def load_sizes(self, key, default):
        """从设置中加载尺寸数据"""
        sizes_json = self.settings.value(key)
        if sizes_json:
            try:
                return json.loads(sizes_json)
            except json.JSONDecodeError:
                pass
        return default
    
    def save_sizes(self):
        """保存尺寸数据到设置"""
        self.settings.setValue("photo_sizes", json.dumps(self.photo_sizes))
        self.settings.setValue("canvas_sizes", json.dumps(self.canvas_sizes))
    
    def get_photo_size(self, index):
        """获取照片尺寸"""
        if 0 <= index < len(self.photo_sizes):
            return self.photo_sizes[index]
        return None
    
    def get_canvas_size(self, index):
        """获取画布尺寸"""
        if 0 <= index < len(self.canvas_sizes):
            return self.canvas_sizes[index]
        return None
    
    def add_photo_size(self, name, width, height):
        """添加自定义照片尺寸"""
        self.photo_sizes.append({
            "name": name,
            "width": width,
            "height": height
        })
        self.save_sizes()
    
    def add_canvas_size(self, name, width, height):
        """添加自定义画布尺寸"""
        self.canvas_sizes.append({
            "name": name,
            "width": width,
            "height": height
        })
        self.save_sizes()

class SizeEditorDialog(QDialog):
    """尺寸编辑对话框"""
    def __init__(self, parent=None, size_type="photo", size_manager=None):
        super().__init__(parent)
        self.size_manager = size_manager
        self.size_type = size_type
        self.setWindowTitle(f"添加自定义{size_type}尺寸")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.width_edit = QLineEdit()
        self.height_edit = QLineEdit()
        
        form_layout.addRow("名称:", self.name_edit)
        form_layout.addRow("宽度 (cm):", self.width_edit)
        form_layout.addRow("高度 (cm):", self.height_edit)
        
        layout.addLayout(form_layout)
        
        # 按钮区域
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_size(self):
        """获取编辑后的尺寸"""
        try:
            name = self.name_edit.text().strip()
            width = float(self.width_edit.text())
            height = float(self.height_edit.text())
            
            if not name:
                raise ValueError("名称不能为空")
                
            if width <= 0 or height <= 0:
                raise ValueError("尺寸必须大于0")
                
            return name, width, height
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
            return None, None, None

class EnhancedPhotoLayoutTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("专业证件照片排版工具")
        self.setGeometry(100, 100, 1100, 700)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                border: 1px solid #dcdfe6;
                border-radius: 8px;
                margin-top: 1ex;
                font-weight: bold;
                padding: 12px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                font-size: 13px;
                color: #409eff;
            }
            QLabel {
                font-size: 12px;
                color: #606266;
            }
            QComboBox, QLineEdit {
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                min-height: 28px;
                background-color: white;
            }
            QComboBox:hover, QLineEdit:hover {
                border-color: #c0c4cc;
            }
            QComboBox:focus, QLineEdit:focus {
                border: 1px solid #409eff;
                box-shadow: 0 0 3px rgba(64, 158, 255, 0.3);
            }
            QPushButton {
                background-color: #409eff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 500;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
            QPushButton:pressed {
                background-color: #3a8ee6;
            }
            QPushButton#actionButton {
                background-color: #67c23a;
            }
            QPushButton#actionButton:hover {
                background-color: #85ce61;
            }
            QRadioButton {
                font-size: 12px;
                color: #606266;
                padding: 4px 0;
            }
            #previewArea {
                background-color: #ebeef5;
                border: 1px solid #dcdfe6;
                border-radius: 8px;
            }
            .statsLabel {
                font-size: 11px;
                color: #909399;
                background-color: rgba(255, 255, 255, 0.7);
                border-radius: 4px;
                padding: 2px 6px;
            }
            QScrollArea {
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: #f0f0f0;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #c0c0c0;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        # 初始化尺寸管理器
        self.size_manager = SizeManager()
        
        # 初始化变量 - 所有尺寸统一为(宽度, 高度)格式
        self.photo_size = self.size_manager.get_photo_size(0)  # 默认第一个照片尺寸
        self.canvas_size = self.size_manager.get_canvas_size(0)  # 默认第一个画布尺寸
        self.spacing = (0.5, 0.5)  # 间距 (水平, 垂直) 单位厘米
        self.dpi = 300  # 默认DPI
        self.photo_pixmap = None
        self.orientation_mode = 0  # 0:自动, 1:横向(短边垂直), 2:竖向(短边水平)
        
        # 创建主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # 左侧控制面板 - 放入滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        
        control_container = QWidget()
        control_layout = QVBoxLayout(control_container)
        control_layout.setContentsMargins(5, 5, 15, 5)  # 右侧留出空间给滚动条
        control_layout.setSpacing(18)
        
        # 标题
        title_label = QLabel("专业证件照片排版工具")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #303133;")
        subtitle_label = QLabel("自定义照片尺寸、打印画布尺寸，智能排版，最大化利用纸张")
        subtitle_label.setStyleSheet("font-size: 14px; color: #909399;")
        
        # 证件照片尺寸设置
        photo_size_group = QGroupBox("证件照片尺寸")
        photo_layout = QVBoxLayout(photo_size_group)
        
        photo_hbox = QHBoxLayout()
        self.photo_size_combo = QComboBox()
        self.populate_photo_sizes()
        self.photo_size_combo.currentIndexChanged.connect(self.update_photo_size)
        photo_hbox.addWidget(self.photo_size_combo, 5)
        
        self.add_photo_btn = QPushButton("+")
        self.add_photo_btn.setMaximumWidth(40)
        self.add_photo_btn.setToolTip("添加自定义尺寸")
        self.add_photo_btn.clicked.connect(self.add_custom_photo_size)
        photo_hbox.addWidget(self.add_photo_btn)
        
        photo_layout.addLayout(photo_hbox)
        
        # 冲洗照片尺寸设置
        canvas_size_group = QGroupBox("冲洗照片尺寸")
        canvas_layout = QVBoxLayout(canvas_size_group)
        
        canvas_hbox = QHBoxLayout()
        self.canvas_size_combo = QComboBox()
        self.populate_canvas_sizes()
        self.canvas_size_combo.currentIndexChanged.connect(self.update_canvas_size)
        canvas_hbox.addWidget(self.canvas_size_combo, 5)
        
        self.add_canvas_btn = QPushButton("+")
        self.add_canvas_btn.setMaximumWidth(40)
        self.add_canvas_btn.setToolTip("添加自定义尺寸")
        self.add_canvas_btn.clicked.connect(self.add_custom_canvas_size)
        canvas_hbox.addWidget(self.add_canvas_btn)
        
        canvas_layout.addLayout(canvas_hbox)
        
        # 纸张方向设置
        orientation_group = QGroupBox("纸张方向")
        orientation_layout = QVBoxLayout(orientation_group)
        
        self.orientation_auto = QRadioButton("自动 (智能优化)")
        self.orientation_auto.setChecked(True)
        self.orientation_horizontal = QRadioButton("横向 (短边垂直)")
        self.orientation_vertical = QRadioButton("竖向 (短边水平)")
        
        self.orientation_group = QButtonGroup(self)
        self.orientation_group.addButton(self.orientation_auto, 0)
        self.orientation_group.addButton(self.orientation_horizontal, 1)
        self.orientation_group.addButton(self.orientation_vertical, 2)
        self.orientation_group.buttonClicked.connect(self.update_orientation)
        
        orientation_layout.addWidget(self.orientation_auto)
        orientation_layout.addWidget(self.orientation_horizontal)
        orientation_layout.addWidget(self.orientation_vertical)
        
        # 照片间距设置
        spacing_group = QGroupBox("照片间距设置")
        spacing_layout = QVBoxLayout(spacing_group)
        
        spacing_form = QGridLayout()
        spacing_form.setHorizontalSpacing(12)
        spacing_form.setVerticalSpacing(10)
        
        spacing_form.addWidget(QLabel("水平间距 (cm):"), 0, 0)
        self.h_spacing_edit = QLineEdit("0.5")
        self.h_spacing_edit.textChanged.connect(self.update_spacing)
        spacing_form.addWidget(self.h_spacing_edit, 0, 1)
        
        spacing_form.addWidget(QLabel("垂直间距 (cm):"), 1, 0)
        self.v_spacing_edit = QLineEdit("0.5")
        self.v_spacing_edit.textChanged.connect(self.update_spacing)
        spacing_form.addWidget(self.v_spacing_edit, 1, 1)
        
        spacing_layout.addLayout(spacing_form)
        
        # 上传照片
        upload_group = QGroupBox("上传证件照片")
        upload_layout = QVBoxLayout(upload_group)
        self.upload_btn = QPushButton("选择照片文件")
        self.upload_btn.clicked.connect(self.upload_photo)
        self.upload_label = QLabel("未选择文件")
        self.upload_label.setStyleSheet("font-size: 11px; color: #909399; margin-top: 5px;")
        upload_layout.addWidget(self.upload_btn)
        upload_layout.addWidget(self.upload_label)
        
        # 保存设置
        save_group = QGroupBox("输出设置")
        save_layout = QVBoxLayout(save_group)
        
        save_form = QGridLayout()
        save_form.setHorizontalSpacing(12)
        save_form.setVerticalSpacing(10)
        
        save_form.addWidget(QLabel("DPI (打印质量):"), 0, 0)
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["150 (普通)", "300 (标准)", "600 (高质量)", "1200 (超高质量)"])
        self.dpi_combo.setCurrentIndex(1)
        self.dpi_combo.currentIndexChanged.connect(self.update_dpi)
        save_form.addWidget(self.dpi_combo, 0, 1)
        
        save_form.addWidget(QLabel("保存格式:"), 1, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG (推荐)", "JPG", "BMP", "TIFF"])
        save_form.addWidget(self.format_combo, 1, 1)
        
        save_layout.addLayout(save_form)
        
        # 生成按钮
        generate_btn = QPushButton("生成并下载排版")
        generate_btn.setObjectName("actionButton")
        generate_btn.clicked.connect(self.generate_layout)
        
        # 添加到左侧布局
        control_layout.addWidget(title_label)
        control_layout.addWidget(subtitle_label)
        control_layout.addWidget(photo_size_group)
        control_layout.addWidget(canvas_size_group)
        control_layout.addWidget(orientation_group)
        control_layout.addWidget(spacing_group)
        control_layout.addWidget(upload_group)
        control_layout.addWidget(save_group)
        control_layout.addWidget(generate_btn)
        control_layout.addStretch(1)  # 添加弹性空间
        
        # 设置滚动区域的内容
        scroll_area.setWidget(control_container)
        
        # 右侧预览区域
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(15)
        
        preview_title = QLabel("排版预览")
        preview_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #303133;")
        
        self.preview_area = QLabel()
        self.preview_area.setObjectName("previewArea")
        self.preview_area.setAlignment(Qt.AlignCenter)
        self.preview_area.setMinimumSize(650, 550)
        
        # 统计信息区域
        self.stats_area = QWidget()
        stats_layout = QHBoxLayout(self.stats_area)
        stats_layout.setContentsMargins(10, 5, 10, 5)
        
        self.stats_label1 = QLabel("照片尺寸: -")
        self.stats_label1.setObjectName("statsLabel")
        self.stats_label1.setAlignment(Qt.AlignCenter)
        
        self.stats_label2 = QLabel("画布尺寸: -")
        self.stats_label2.setObjectName("statsLabel")
        self.stats_label2.setAlignment(Qt.AlignCenter)
        
        self.stats_label3 = QLabel("排列: -")
        self.stats_label3.setObjectName("statsLabel")
        self.stats_label3.setAlignment(Qt.AlignCenter)
        
        self.stats_label4 = QLabel("方向: -")
        self.stats_label4.setObjectName("statsLabel")
        self.stats_label4.setAlignment(Qt.AlignCenter)
        
        stats_layout.addWidget(self.stats_label1)
        stats_layout.addWidget(self.stats_label2)
        stats_layout.addWidget(self.stats_label3)
        stats_layout.addWidget(self.stats_label4)
        
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview_area, 1)
        preview_layout.addWidget(self.stats_area)
        
        # 添加到主布局
        main_layout.addWidget(scroll_area)  # 使用滚动区域替代原控制面板
        main_layout.addWidget(preview_panel, 1)
        
        # 初始预览
        self.update_preview()
    
    def populate_photo_sizes(self):
        """填充照片尺寸选项"""
        self.photo_size_combo.clear()
        for size in self.size_manager.photo_sizes:
            self.photo_size_combo.addItem(
                f"{size['name']} ({size['width']}cm×{size['height']}cm)", 
                size
            )
        # 添加自定义选项
        self.photo_size_combo.addItem("添加自定义尺寸...", None)
    
    def populate_canvas_sizes(self):
        """填充画布尺寸选项"""
        self.canvas_size_combo.clear()
        for size in self.size_manager.canvas_sizes:
            self.canvas_size_combo.addItem(
                f"{size['name']}: ({size['width']}cm×{size['height']}cm)", 
                size
            )
        # 添加自定义选项
        self.canvas_size_combo.addItem("添加自定义尺寸...", None)
    
    def update_photo_size(self, index):
        """更新证件照片尺寸"""
        size_data = self.photo_size_combo.itemData(index)
        if size_data is None:
            # 用户选择了"添加自定义尺寸..."
            self.add_custom_photo_size()
        else:
            self.photo_size = size_data
            self.update_preview()
    
    def update_canvas_size(self, index):
        """更新冲洗照片尺寸"""
        size_data = self.canvas_size_combo.itemData(index)
        if size_data is None:
            # 用户选择了"添加自定义尺寸..."
            self.add_custom_canvas_size()
        else:
            self.canvas_size = size_data
            self.update_preview()
    
    def add_custom_photo_size(self):
        """添加自定义照片尺寸"""
        dialog = SizeEditorDialog(self, "照片", self.size_manager)
        if dialog.exec_() == QDialog.Accepted:
            name, width, height = dialog.get_size()
            if name and width and height:
                self.size_manager.add_photo_size(name, width, height)
                self.populate_photo_sizes()
                # 选择新添加的尺寸
                for i in range(self.photo_size_combo.count()):
                    if self.photo_size_combo.itemData(i) and \
                       self.photo_size_combo.itemData(i)["name"] == name:
                        self.photo_size_combo.setCurrentIndex(i)
                        break
    
    def add_custom_canvas_size(self):
        """添加自定义画布尺寸"""
        dialog = SizeEditorDialog(self, "画布", self.size_manager)
        if dialog.exec_() == QDialog.Accepted:
            name, width, height = dialog.get_size()
            if name and width and height:
                self.size_manager.add_canvas_size(name, width, height)
                self.populate_canvas_sizes()
                # 选择新添加的尺寸
                for i in range(self.canvas_size_combo.count()):
                    if self.canvas_size_combo.itemData(i) and \
                       self.canvas_size_combo.itemData(i)["name"] == name:
                        self.canvas_size_combo.setCurrentIndex(i)
                        break
    
    def update_orientation(self, button):
        """更新纸张方向"""
        self.orientation_mode = self.orientation_group.id(button)
        self.update_preview()
    
    def update_spacing(self):
        """更新照片间距"""
        try:
            h_spacing = float(self.h_spacing_edit.text())
            v_spacing = float(self.v_spacing_edit.text())
            if h_spacing >= 0 and v_spacing >= 0:
                self.spacing = (h_spacing, v_spacing)
                self.update_preview()
        except ValueError:
            pass
    
    def update_dpi(self, index):
        """更新DPI设置"""
        dpi_values = [150, 300, 600, 1200]
        self.dpi = dpi_values[index]
        self.update_preview()
    
    def upload_photo(self):
        """上传证件照片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择证件照片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.upload_label.setText(os.path.basename(file_path))
            self.photo_pixmap = QPixmap(file_path)
            self.update_preview()
    
    def cm_to_pixels(self, cm, dpi):
        """将厘米转换为像素"""
        inches = cm / 2.54
        return int(inches * dpi)
    
    def calculate_layout(self):
        """计算最佳排版布局（考虑方向优化）"""
        # 获取物理尺寸
        canvas_phys_w = self.canvas_size["width"]
        canvas_phys_h = self.canvas_size["height"]
        photo_w = self.photo_size["width"]
        photo_h = self.photo_size["height"]
        
        # 自动方向选择：计算两种方向下的照片数量
        if self.orientation_mode == 0:  # 自动
            # 方向1：自然方向
            cols1, rows1 = self.calculate_rows_cols(
                canvas_phys_w, canvas_phys_h, 
                photo_w, photo_h
            )
            count1 = cols1 * rows1
            
            # 方向2：旋转90度方向
            cols2, rows2 = self.calculate_rows_cols(
                canvas_phys_h, canvas_phys_w, 
                photo_w, photo_h
            )
            count2 = cols2 * rows2
            
            # 选择能容纳更多照片的方向
            if count1 >= count2:
                # 使用自然方向
                canvas_w_used, canvas_h_used = canvas_phys_w, canvas_phys_h
                cols, rows = cols1, rows1
                # 确定方向标签（宽边水平为横向，宽边垂直为竖向）
                orientation = "横向" if canvas_phys_w >= canvas_phys_h else "竖向"
            else:
                # 使用旋转方向
                canvas_w_used, canvas_h_used = canvas_phys_h, canvas_phys_w
                cols, rows = cols2, rows2
                # 确定方向标签（宽边水平为横向，宽边垂直为竖向）
                orientation = "横向" if canvas_phys_h >= canvas_phys_w else "竖向"
        elif self.orientation_mode == 1:  # 横向 (短边垂直)
            # 确保宽边水平放置（短边垂直）
            if canvas_phys_w >= canvas_phys_h:
                canvas_w_used, canvas_h_used = canvas_phys_w, canvas_phys_h
            else:
                canvas_w_used, canvas_h_used = canvas_phys_h, canvas_phys_w
            cols, rows = self.calculate_rows_cols(
                canvas_w_used, canvas_h_used, 
                photo_w, photo_h
            )
            orientation = "横向"
        else:  # 竖向 (短边水平)
            # 确保宽边垂直放置（短边水平）
            if canvas_phys_h >= canvas_phys_w:
                canvas_w_used, canvas_h_used = canvas_phys_w, canvas_phys_h
            else:
                canvas_w_used, canvas_h_used = canvas_phys_h, canvas_phys_w
            cols, rows = self.calculate_rows_cols(
                canvas_w_used, canvas_h_used, 
                photo_w, photo_h
            )
            orientation = "竖向"
        
        # 转换为像素
        photo_px_w = self.cm_to_pixels(photo_w, self.dpi)
        photo_px_h = self.cm_to_pixels(photo_h, self.dpi)
        canvas_px_w = self.cm_to_pixels(canvas_w_used, self.dpi)
        canvas_px_h = self.cm_to_pixels(canvas_h_used, self.dpi)
        spacing_px_w = self.cm_to_pixels(self.spacing[0], self.dpi)
        spacing_px_h = self.cm_to_pixels(self.spacing[1], self.dpi)
        
        # 计算总尺寸和边距
        total_w = cols * photo_px_w + max(0, cols - 1) * spacing_px_w
        total_h = rows * photo_px_h + max(0, rows - 1) * spacing_px_h
        margin_x = max(0, (canvas_px_w - total_w) // 2)
        margin_y = max(0, (canvas_px_h - total_h) // 2)
        
        return {
            'canvas_size': (canvas_px_w, canvas_px_h),
            'photo_size': (photo_px_w, photo_px_h),
            'spacing': (spacing_px_w, spacing_px_h),
            'rows': rows,
            'cols': cols,
            'margin': (margin_x, margin_y),
            'total_photos': rows * cols,
            'orientation': orientation,
            'physical_canvas': (canvas_phys_w, canvas_phys_h),
            'physical_photo': (photo_w, photo_h),
            'used_canvas': (canvas_w_used, canvas_h_used)
        }
    
    def calculate_rows_cols(self, canvas_w, canvas_h, photo_w, photo_h):
        """计算给定方向下的行列数"""
        # 物理尺寸（厘米）
        spacing_w, spacing_h = self.spacing

        # 计算列数（考虑间距）
        if photo_w + spacing_w > 0:
            cols = max(1, int((canvas_w + spacing_w) // (photo_w + spacing_w)))
        else:
            cols = 1
        
        # 计算行数（考虑间距）
        if photo_h + spacing_h > 0:
            rows = max(1, int((canvas_h + spacing_h) // (photo_h + spacing_h)))
        else:
            rows = 1
        
        return cols, rows
    
    def update_preview(self):
        """更新预览区域"""
        if not hasattr(self, 'preview_area'):
            return
            
        layout_info = self.calculate_layout()
        canvas_w, canvas_h = layout_info['canvas_size']
        photo_w, photo_h = layout_info['photo_size']
        rows, cols = layout_info['rows'], layout_info['cols']
        spacing_w, spacing_h = layout_info['spacing']
        margin_x, margin_y = layout_info['margin']
        total_photos = layout_info['total_photos']
        orientation = layout_info['orientation']
        
        # 创建预览图像
        preview_img = QImage(canvas_w, canvas_h, QImage.Format_RGB32)
        preview_img.fill(QColor(235, 238, 245))  # 预览背景色
        
        painter = QPainter(preview_img)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制画布边框
        painter.setPen(QPen(QColor(180, 190, 210), 3, Qt.DashLine))
        painter.drawRect(0, 0, canvas_w - 1, canvas_h - 1)
        
        # 绘制照片位置
        painter.setBrush(QBrush(QColor(64, 158, 255, 120)))  # 半透明蓝色
        painter.setPen(QPen(QColor(30, 100, 200), 1))
        
        for row in range(rows):
            for col in range(cols):
                x = margin_x + col * (photo_w + spacing_w)
                y = margin_y + row * (photo_h + spacing_h)
                painter.drawRect(x, y, photo_w, photo_h)
        
        # 如果上传了照片，在第一个位置显示预览
        if self.photo_pixmap and not self.photo_pixmap.isNull():
            # 缩放照片到证件尺寸
            scaled_photo = self.photo_pixmap.scaled(
                photo_w, photo_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )
            # 在第一个位置绘制照片预览
            first_x = margin_x
            first_y = margin_y
            painter.drawPixmap(first_x, first_y, scaled_photo)
        
        # 绘制方向指示
        if orientation == "横向":
            # 横向指示器（箭头向右）
            painter.setPen(QPen(Qt.darkGreen, 2, Qt.SolidLine))
            painter.drawLine(20, 20, 50, 20)
            painter.drawLine(50, 20, 45, 15)
            painter.drawLine(50, 20, 45, 25)
            painter.drawText(55, 25, "纸张方向: 横向 (短边垂直)")
        else:
            # 竖向指示器（箭头向下）
            painter.setPen(QPen(Qt.darkBlue, 2, Qt.SolidLine))
            painter.drawLine(20, 20, 20, 50)
            painter.drawLine(20, 50, 15, 45)
            painter.drawLine(20, 50, 25, 45)
            painter.drawText(25, 60, "纸张方向: 竖向 (短边水平)")
        
        painter.end()
        
        # 缩放预览以适应显示区域
        preview_pixmap = QPixmap.fromImage(preview_img)
        preview_size = self.preview_area.size()
        scaled_pixmap = preview_pixmap.scaled(
            preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        
        self.preview_area.setPixmap(scaled_pixmap)
        
        # 更新统计信息
        ph_w, ph_h = layout_info['physical_photo']
        cv_w, cv_h = layout_info['physical_canvas']
        
        self.stats_label1.setText(f"照片尺寸: {ph_w}×{ph_h}cm")
        self.stats_label2.setText(f"画布尺寸: {cv_w}×{cv_h}cm")
        self.stats_label3.setText(f"排列: {rows}行 × {cols}列 = {total_photos}张")
        self.stats_label4.setText(f"方向: {orientation}")
    
    def generate_layout(self):
        """生成并下载排版"""
        if not self.photo_pixmap or self.photo_pixmap.isNull():
            QMessageBox.warning(self, "警告", "请先上传证件照片！")
            return
            
        layout_info = self.calculate_layout()
        canvas_w, canvas_h = layout_info['canvas_size']
        photo_w, photo_h = layout_info['photo_size']
        rows, cols = layout_info['rows'], layout_info['cols']
        spacing_w, spacing_h = layout_info['spacing']
        margin_x, margin_y = layout_info['margin']
        
        # 创建最终图像
        result_img = QImage(canvas_w, canvas_h, QImage.Format_RGB32)
        result_img.fill(Qt.white)  # 白色背景
        
        painter = QPainter(result_img)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # 缩放照片到证件尺寸
        scaled_photo = self.photo_pixmap.scaled(
            photo_w, photo_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        
        # 排列照片
        for row in range(rows):
            for col in range(cols):
                x = margin_x + col * (photo_w + spacing_w)
                y = margin_y + row * (photo_h + spacing_h)
                painter.drawPixmap(x, y, scaled_photo)
        
        painter.end()
        
        # 保存文件
        format_map = {
            "PNG (推荐)": "PNG",
            "JPG": "JPG",
            "BMP": "BMP",
            "TIFF": "TIFF"
        }
        selected_format = self.format_combo.currentText()
        file_format = format_map.get(selected_format, "PNG")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存排版照片", f"证件照片排版.{file_format.lower()}",
            f"{file_format}文件 (*.{file_format.lower()})"
        )
        
        if file_path:
            result_img.save(file_path, file_format)
            QMessageBox.information(self, "成功", f"证件照片排版已保存至:\n{file_path}")
    
    def resizeEvent(self, event):
        """窗口大小改变时更新预览"""
        super().resizeEvent(event)
        self.update_preview()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EnhancedPhotoLayoutTool()
    window.show()
    sys.exit(app.exec_())