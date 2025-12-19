import sys
import math
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QComboBox, 
                            QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QGroupBox, QFileDialog, QLineEdit, QMessageBox)
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush
from PyQt5.QtCore import Qt, QSize

class PhotoLayoutTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("在线证件照片排版")
        self.setGeometry(100, 100, 1000, 650)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                border: 1px solid #dcdfe6;
                border-radius: 6px;
                margin-top: 1ex;
                font-weight: bold;
                padding: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
            QLabel {
                font-size: 12px;
                color: #606266;
            }
            QComboBox, QLineEdit {
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
                min-height: 24px;
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
                padding: 8px 15px;
                font-size: 13px;
                font-weight: 500;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
            QPushButton:pressed {
                background-color: #3a8ee6;
            }
            #previewArea {
                background-color: #ebeef5;
                border: 1px solid #dcdfe6;
                border-radius: 6px;
            }
        """)
        
        # 初始化变量
        self.photo_size = (2.5, 3.5)  # 默认1寸照片 (宽, 高) 单位厘米
        self.canvas_size = (15.2, 10.2)  # 默认6寸画布 (宽, 高) 单位厘米
        self.spacing = (0.5, 0.5)  # 间距 (水平, 垂直) 单位厘米
        self.dpi = 300  # 默认DPI
        self.photo_pixmap = None
        
        # 创建主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # 左侧控制面板
        control_panel = QWidget()
        control_panel.setFixedWidth(320)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("在线证件照片排版")
        title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #303133;")
        subtitle_label = QLabel("可自定义照片尺寸、打印画布尺寸，一键排版，轻松打印")
        subtitle_label.setStyleSheet("font-size: 13px; color: #909399;")
        
        # 证件照片尺寸设置
        photo_size_group = QGroupBox("选择证件照片尺寸")
        photo_layout = QVBoxLayout(photo_size_group)
        self.photo_size_combo = QComboBox()
        self.photo_size_combo.addItems(["1寸 (2.5cm×3.5cm)", "2寸 (3.5cm×4.9cm)", "小1寸 (2.2cm×3.2cm)", 
                                       "大1寸 (3.3cm×4.8cm)", "5寸 (12.7cm×8.9cm)", "自定义尺寸"])
        self.photo_size_combo.currentIndexChanged.connect(self.update_photo_size)
        photo_layout.addWidget(self.photo_size_combo)
        
        # 冲洗照片尺寸设置
        canvas_size_group = QGroupBox("选择冲洗照片尺寸")
        canvas_layout = QVBoxLayout(canvas_size_group)
        self.canvas_size_combo = QComboBox()
        self.canvas_size_combo.addItems(["6寸(4R):(15.2cm×10.2cm)", "5寸(3R):(12.7cm×8.9cm)", 
                                        "7寸(5R):(17.8cm×12.7cm)", "A4:(21cm×29.7cm)", "自定义尺寸"])
        self.canvas_size_combo.currentIndexChanged.connect(self.update_canvas_size)
        canvas_layout.addWidget(self.canvas_size_combo)
        
        # 照片间距设置
        spacing_group = QGroupBox("照片间距设置")
        spacing_layout = QVBoxLayout(spacing_group)
        
        spacing_form = QGridLayout()
        spacing_form.setHorizontalSpacing(10)
        spacing_form.setVerticalSpacing(8)
        
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
        self.upload_btn = QPushButton("选择文件")
        self.upload_btn.clicked.connect(self.upload_photo)
        self.upload_label = QLabel("未选择文件")
        self.upload_label.setStyleSheet("font-size: 11px; color: #909399; margin-top: 5px;")
        upload_layout.addWidget(self.upload_btn)
        upload_layout.addWidget(self.upload_label)
        
        # 保存格式
        format_group = QGroupBox("选择保存格式")
        format_layout = QVBoxLayout(format_group)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPG", "BMP"])
        format_layout.addWidget(self.format_combo)
        
        # 生成按钮
        generate_btn = QPushButton("生成并下载排版")
        generate_btn.setStyleSheet("background-color: #67c23a;")
        generate_btn.clicked.connect(self.generate_layout)
        
        # 添加到左侧布局
        control_layout.addWidget(title_label)
        control_layout.addWidget(subtitle_label)
        control_layout.addWidget(photo_size_group)
        control_layout.addWidget(canvas_size_group)
        control_layout.addWidget(spacing_group)
        control_layout.addWidget(upload_group)
        control_layout.addWidget(format_group)
        control_layout.addWidget(generate_btn)
        control_layout.addStretch()
        
        # 右侧预览区域
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        preview_title = QLabel("排版预览")
        preview_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #303133;")
        
        self.preview_area = QLabel()
        self.preview_area.setObjectName("previewArea")
        self.preview_area.setAlignment(Qt.AlignCenter)
        self.preview_area.setMinimumSize(600, 500)
        self.preview_area.setStyleSheet("""
            #previewArea {
                background-color: #ebeef5;
                border: 1px solid #dcdfe6;
                border-radius: 6px;
            }
        """)
        
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview_area, 1)
        
        # 添加到主布局
        main_layout.addWidget(control_panel)
        main_layout.addWidget(preview_panel, 1)
        
        # 初始预览
        self.update_preview()
    
    def update_photo_size(self, index):
        """更新证件照片尺寸"""
        sizes = [
            (2.5, 3.5),   # 1寸
            (3.5, 4.9),   # 2寸
            (2.2, 3.2),   # 小1寸
            (3.3, 4.8),   # 大1寸
            (12.7, 8.9),  # 5寸
            self.photo_size  # 自定义（保持原值）
        ]
        self.photo_size = sizes[index]
        self.update_preview()
    
    def update_canvas_size(self, index):
        """更新冲洗照片尺寸"""
        sizes = [
            (15.2, 10.2),  # 6寸
            (12.7, 8.9),   # 5寸
            (17.8, 12.7),  # 7寸
            (21.0, 29.7),  # A4
            self.canvas_size  # 自定义（保持原值）
        ]
        self.canvas_size = sizes[index]
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
    
    def upload_photo(self):
        """上传证件照片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择证件照片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.upload_label.setText(file_path.split('/')[-1])
            self.photo_pixmap = QPixmap(file_path)
            self.update_preview()
    
    def cm_to_pixels(self, cm, dpi):
        """将厘米转换为像素"""
        inches = cm / 2.54
        return int(inches * dpi)
    
    def calculate_layout(self):
        """计算最佳排版布局"""
        # 转换为像素
        photo_w = self.cm_to_pixels(self.photo_size[0], self.dpi)
        photo_h = self.cm_to_pixels(self.photo_size[1], self.dpi)
        canvas_w = self.cm_to_pixels(self.canvas_size[0], self.dpi)
        canvas_h = self.cm_to_pixels(self.canvas_size[1], self.dpi)
        spacing_w = self.cm_to_pixels(self.spacing[0], self.dpi)
        spacing_h = self.cm_to_pixels(self.spacing[1], self.dpi)

        # 计算可容纳的照片数量（横向和纵向）
        if photo_w + spacing_w > 0:
            cols = max(1, (canvas_w + spacing_w) // (photo_w + spacing_w))
        else:
            cols = 1
            
        if photo_h + spacing_h > 0:
            rows = max(1, (canvas_h + spacing_h) // (photo_h + spacing_h))
        else:
            rows = 1

        # 计算边距（居中）
        total_w = cols * photo_w + (cols - 1) * spacing_w
        total_h = rows * photo_h + (rows - 1) * spacing_h
        margin_x = (canvas_w - total_w) // 2
        margin_y = (canvas_h - total_h) // 2
        
        # 确定方向
        canvas_physical_width = round(self.canvas_size[0], 1)
        canvas_physical_height = round(self.canvas_size[1], 1)
        if canvas_physical_width > canvas_physical_height:
            orientation = "横向"
        else:
            orientation = "竖向"
        
        return {
            'canvas_size': (canvas_w, canvas_h),
            'photo_size': (photo_w, photo_h),
            'spacing': (spacing_w, spacing_h),
            'rows': rows,
            'cols': cols,
            'margin': (margin_x, margin_y),
            'total_photos': rows * cols,
            'orientation': orientation,
            'physical_photo': (round(self.photo_size[0], 1), round(self.photo_size[1], 1)),
            'physical_canvas': (canvas_physical_width, canvas_physical_height)
        }
    
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

        # 如果画布宽度或高度为0，则不进行绘制
        if canvas_w <= 0 or canvas_h <= 0:
            return

        # 创建预览图像
        preview_img = QImage(canvas_w, canvas_h, QImage.Format_RGB32)
        if preview_img.isNull():
            return
        
        preview_img.fill(QColor(235, 238, 245))  # 预览背景色
        painter = QPainter(preview_img)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制画布边框
        painter.setPen(QPen(QColor(220, 223, 230), 2))
        painter.drawRect(0, 0, canvas_w - 1, canvas_h - 1)
        
        # 绘制照片位置
        painter.setBrush(QBrush(QColor(64, 158, 255, 180)))  # 半透明蓝色
        painter.setPen(QPen(QColor(220, 223, 230), 1))
        
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
            painter.setPen(QPen(Qt.GlobalColor.darkGreen, 2, Qt.PenStyle.SolidLine))
            painter.drawLine(20, 20, 50, 20)
            painter.drawLine(50, 20, 45, 15)
            painter.drawLine(50, 20, 45, 25)
            painter.drawText(55, 25, "纸张方向: 横向 (短边垂直)")
        else:
            # 竖向指示器（箭头向下）
            painter.setPen(QPen(Qt.GlobalColor.darkBlue, 2, Qt.PenStyle.SolidLine))
            painter.drawLine(20, 20, 20, 50)
            painter.drawLine(20, 50, 15, 45)
            painter.drawLine(20, 50, 25, 45)
            painter.drawText(25, 60, "纸张方向: 竖向 (短边水平)")

        painter.end()
        
        # 缩放预览以适应显示区域
        preview_pixmap = QPixmap.fromImage(preview_img)
        preview_size = self.preview_area.size()
        if preview_size.width() <= 0 or preview_size.height() <= 0:
            return
        
        scaled_pixmap = preview_pixmap.scaled(
            preview_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.preview_area.setPixmap(scaled_pixmap)

        # 更新状态栏信息
        self.statusBar().showMessage(
            f"排版: {rows}行 × {cols}列 = {total_photos}张照片 | "
            f"画布尺寸: {self.canvas_size[0]}×{self.canvas_size[1]}cm | "
            f"照片尺寸: {self.photo_size[0]}×{self.photo_size[1]}cm"
        )
    
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
        file_format = self.format_combo.currentText()
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
    window = PhotoLayoutTool()
    window.show()
    sys.exit(app.exec_())