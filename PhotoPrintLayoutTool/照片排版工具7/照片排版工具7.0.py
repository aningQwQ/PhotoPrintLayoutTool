# -*- coding: utf-8 -*-
"""
专业证件照片排版工具 - 增强版
支持多照片上传、混合尺寸排版、批量导出
"""

import sys
import json
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QComboBox, 
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QFileDialog, QLineEdit, QMessageBox,
    QRadioButton, QButtonGroup, QScrollArea, QListWidget,
    QListWidgetItem, QCheckBox, QProgressBar, QSpinBox,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsItem, QDockWidget, QToolBar, QStatusBar,
    QDialog, QDialogButtonBox, QSplitter, QFrame
)
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QBrush, QFont,
    QDragEnterEvent, QDropEvent, QCursor, QIcon
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer, QRectF

# 尝试导入rectpack库用于bin packing算法
try:
    import rectpack
    HAS_RECTPACK = True
except ImportError:
    HAS_RECTPACK = False


class PhotoSource:
    """照片数据模型"""
    def __init__(self, file_path, pixmap):
        self.id = id(self)
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.original_pixmap = pixmap
        # 每个照片的排版参数
        self.target_size_index = 0  # 默认使用第一个尺寸
        self.quantity = 1  # 默认数量


class PhotoItem(QGraphicsPixmapItem):
    """画布上的照片项，支持拖拽"""
    def __init__(self, photo_source, width_px, height_px, parent=None):
        super().__init__(parent)
        self.photo_source = photo_source
        self.target_width = width_px
        self.target_height = height_px
        
        # 缩放照片
        scaled = photo_source.original_pixmap.scaled(
            width_px, height_px, 
            Qt.AspectRatioMode.IgnoreAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled)
        
        # 设置项标志
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        
        # 初始位置
        self.setOffset(0, 0)
    
    def itemChange(self, change, value):
        """处理位置变化"""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # 可以添加对齐辅助线等效果
            pass
        return super().itemChange(change, value)


class LayoutWorker(QThread):
    """后台布局计算线程"""
    progress = Signal(int)
    finished = Signal(list)  # 返回布局位置列表
    
    def __init__(self, photo_sources, canvas_width, canvas_height, spacing_px):
        super().__init__()
        self.photo_sources = photo_sources
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.spacing_px = spacing_px
    
    def run(self):
        """执行布局计算"""
        layout_items = []
        
        # 收集所有需要排列的矩形
        rects = []
        for i, photo in enumerate(self.photo_sources):
            # 获取目标尺寸
            size_info = size_manager.get_photo_size(photo.target_size_index)
            if size_info:
                w = size_info["width"]
                h = size_info["height"]
                # 转换为像素
                w_px = self.cm_to_px(w)
                h_px = self.cm_to_px(h)
                
                for q in range(photo.quantity):
                    rects.append((w_px + self.spacing_px, h_px + self.spacing_px, i, q))
            
            self.progress.emit(int((i + 1) / len(self.photo_sources) * 50))
        
        if not rects:
            self.finished.emit([])
            return
        
        # 使用简单的贪心算法进行bin packing
        # 如果有rectpack库，使用更高效的算法
        if HAS_RECTPACK:
            packer = rectpack.newPacker(rotation=False)
            for r in rects:
                packer.add_rect(r[0], r[1])
            packer.add_bin(self.canvas_width, self.canvas_height)
            bins = packer.pack()
            
            for bin in bins:
                for rect in bin:
                    layout_items.append({
                        'x': rect.x,
                        'y': rect.y,
                        'width': rect.width - self.spacing_px,
                        'height': rect.height - self.spacing_px,
                        'source_index': rect.rid[2],
                        'rotation': rect.rot
                    })
        else:
            # 使用简单的贪心算法
            layout_items = self.greedy_pack(rects)
        
        self.progress.emit(100)
        self.finished.emit(layout_items)
    
    def cm_to_px(self, cm):
        """厘米转像素"""
        inches = cm / 2.54
        return int(inches * 300)  # 默认300 DPI
    
    def greedy_pack(self, rects):
        """贪心算法进行矩形装箱"""
        # 按高度降序排序
        rects = sorted(rects, key=lambda x: x[1], reverse=True)
        
        # 可用空间列表，每个元素是(x, y, width, height)
        spaces = [(0, 0, self.canvas_width, self.canvas_height)]
        placed = []
        
        for w, h, source_idx, quantity_idx in rects:
            best_space = None
            best_area = float('inf')
            
            for i, space in enumerate(spaces):
                if space[2] >= w and space[3] >= h:
                    # 计算剩余空间面积
                    remaining = (space[2] - w) * (space[3] - h)
                    if remaining < best_area:
                        best_area = remaining
                        best_space = (i, space)
            
            if best_space:
                idx, space = best_space
                # 放置矩形
                placed.append({
                    'x': space[0],
                    'y': space[1],
                    'width': w - self.spacing_px,
                    'height': h - self.spacing_px,
                    'source_index': source_idx,
                    'rotation': False
                })
                
                # 更新可用空间
                new_spaces = []
                for i, s in enumerate(spaces):
                    if i == idx:
                        # 分割剩余空间
                        right_space = (space[0] + w, space[1], space[2] - w, space[3])
                        bottom_space = (space[0], space[1] + h, w, space[3] - h)
                        if right_space[2] > 0 and right_space[3] > 0:
                            new_spaces.append(right_space)
                        if bottom_space[2] > 0 and bottom_space[3] > 0:
                            new_spaces.append(bottom_space)
                    else:
                        new_spaces.append(s)
                spaces = new_spaces
        
        return placed


class ExportWorker(QThread):
    """后台导出线程"""
    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, scene, canvas_width, canvas_height, dpi, formats, output_dir, base_name):
        super().__init__()
        self.scene = scene
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.dpi = dpi
        self.formats = formats
        self.output_dir = output_dir
        self.base_name = base_name
    
    def run(self):
        """执行导出"""
        try:
            total = len(self.formats)
            for i, fmt in enumerate(self.formats):
                # 创建高质量图像
                img = QImage(self.canvas_width, self.canvas_height, QImage.Format.Format_RGB32)
                img.fill(Qt.GlobalColor.white)
                
                painter = QPainter(img)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                
                # 渲染场景
                self.scene.render(painter)
                painter.end()
                
                # 保存文件
                ext = fmt.lower()
                file_path = os.path.join(self.output_dir, f"{self.base_name}.{ext}")
                
                if ext == "jpg" or ext == "jpeg":
                    img.save(file_path, fmt, 95)
                else:
                    img.save(file_path, fmt)
                
                self.progress.emit(int((i + 1) / total * 100))
            
            self.finished.emit(self.output_dir)
        except Exception as e:
            self.error.emit(str(e))


class SizeManager:
    """尺寸管理器"""
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
        {"name": "5寸(3R)", "width": 8.9, "height": 12.7},
        {"name": "6寸(4R)", "width": 10.2, "height": 15.2},
        {"name": "7寸(5R)", "width": 12.7, "height": 17.8},
        {"name": "A4", "width": 21.0, "height": 29.7},
        {"name": "A5", "width": 14.8, "height": 21.0},
        {"name": "A6", "width": 10.5, "height": 14.8},
    ]
    
    def __init__(self):
        self.config_file = "photo_layout_config.json"
        self.photo_sizes = self.DEFAULT_PHOTO_SIZES
        self.canvas_sizes = self.DEFAULT_CANVAS_SIZES
        self.load_sizes()
    
    def load_sizes(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.photo_sizes = config.get("photo_sizes", self.DEFAULT_PHOTO_SIZES)
                    self.canvas_sizes = config.get("canvas_sizes", self.DEFAULT_CANVAS_SIZES)
            except (json.JSONDecodeError, IOError):
                self.photo_sizes = self.DEFAULT_PHOTO_SIZES
                self.canvas_sizes = self.DEFAULT_CANVAS_SIZES
    
    def save_sizes(self):
        config = {
            "photo_sizes": self.photo_sizes,
            "canvas_sizes": self.canvas_sizes
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except IOError:
            return False
    
    def get_photo_size(self, index):
        if 0 <= index < len(self.photo_sizes):
            return self.photo_sizes[index]
        return None
    
    def get_canvas_size(self, index):
        if 0 <= index < len(self.canvas_sizes):
            return self.canvas_sizes[index]
        return None


# 全局尺寸管理器
size_manager = SizeManager()


class PhotoListWidget(QListWidget):
    """支持拖拽的照片列表组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.photo_sources = []  # 存储PhotoSource对象
        self.main_window = None
    
    def set_main_window(self, main_window):
        self.main_window = main_window
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("QListWidget { border: 2px dashed #409eff; background: #e6f7ff; }")
    
    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
    
    def dropEvent(self, event):
        self.setStyleSheet("")
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                files.append(file_path)
        
        if files and self.main_window:
            self.main_window.add_photos(files)


class PhotoListItemWidget(QWidget):
    """照片列表项的自定义组件"""
    def __init__(self, photo_source, parent=None):
        super().__init__(parent)
        self.photo_source = photo_source
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        # 缩略图
        thumbnail_label = QLabel()
        thumb = self.photo_source.original_pixmap.scaled(
            60, 60, Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        thumbnail_label.setPixmap(thumb)
        thumbnail_label.setFixedSize(60, 60)
        layout.addWidget(thumbnail_label)
        
        # 信息区域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        
        # 文件名
        name_label = QLabel(self.photo_source.file_name)
        name_label.setStyleSheet("font-weight: bold;")
        name_label.setToolTip(self.photo_source.file_path)
        info_layout.addWidget(name_label)
        
        # 尺寸选择和数量
        row_layout = QHBoxLayout()
        row_layout.setSpacing(5)
        
        # 尺寸下拉框
        self.size_combo = QComboBox()
        for size in size_manager.photo_sizes:
            self.size_combo.addItem(f"{size['name']}", size)
        self.size_combo.setCurrentIndex(self.photo_source.target_size_index)
        self.size_combo.setFixedWidth(100)
        
        # 数量输入
        qty_label = QLabel("数量:")
        qty_label.setStyleSheet("font-size: 11px;")
        self.qty_spin = QSpinBox()
        self.qty_spin.setMinimum(1)
        self.qty_spin.setMaximum(100)
        self.qty_spin.setValue(self.photo_source.quantity)
        self.qty_spin.setFixedWidth(50)
        
        row_layout.addWidget(self.size_combo)
        row_layout.addWidget(qty_label)
        row_layout.addWidget(self.qty_spin)
        row_layout.addStretch()
        
        info_layout.addLayout(row_layout)
        layout.addLayout(info_layout)
        
        # 设置最小高度
        self.setMinimumHeight(70)
    
    def get_values(self):
        """获取当前设置的值"""
        self.photo_source.target_size_index = self.size_combo.currentIndex()
        self.photo_source.quantity = self.qty_spin.value()
        return self.photo_source


class EnhancedPhotoLayoutTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("专业证件照片排版工具 - 增强版")
        self.setGeometry(100, 100, 1200, 800)
        
        self.photo_sources = []  # 所有上传的照片
        self.layout_worker = None
        self.export_worker = None
        
        self.init_ui()
        self.apply_stylesheet()
    
    def init_ui(self):
        """初始化UI"""
        # 创建主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧面板 - 照片管理
        left_panel = self.create_photo_manager_panel()
        splitter.addWidget(left_panel)
        
        # 中间面板 - 画布预览
        center_panel = self.create_canvas_panel()
        splitter.addWidget(center_panel)
        
        # 右侧面板 - 设置和控制
        right_panel = self.create_control_panel()
        splitter.addWidget(right_panel)
        
        # 设置分割比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        
        self.setCentralWidget(splitter)
        
        # 状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪")
    
    def create_photo_manager_panel(self):
        """创建照片管理面板"""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("照片管理")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #303133;")
        layout.addWidget(title)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        add_btn = QPushButton("添加照片")
        add_btn.clicked.connect(self.select_photos)
        toolbar.addWidget(add_btn)
        
        clear_btn = QPushButton("清空全部")
        clear_btn.clicked.connect(self.clear_all_photos)
        toolbar.addWidget(clear_btn)
        
        layout.addLayout(toolbar)
        
        # 提示文字
        hint = QLabel("拖拽照片到下方列表或点击添加按钮")
        hint.setStyleSheet("font-size: 11px; color: #909399; padding: 5px;")
        layout.addWidget(hint)
        
        # 照片列表（支持拖拽）
        self.photo_list = PhotoListWidget()
        self.photo_list.set_main_window(self)
        layout.addWidget(self.photo_list)
        
        return panel
    
    def create_canvas_panel(self):
        """创建画布预览面板"""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 标题栏
        header = QHBoxLayout()
        title = QLabel("排版预览")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        
        # 自动排版按钮
        auto_layout_btn = QPushButton("自动排版")
        auto_layout_btn.clicked.connect(self.auto_layout)
        auto_layout_btn.setStyleSheet("""
            QPushButton {
                background-color: #67c23a;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #85ce61; }
        """)
        header.addWidget(auto_layout_btn, alignment=Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(header)
        
        # 画布视图
        self.canvas_view = QGraphicsView()
        self.canvas_view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.canvas_view.setAcceptDrops(True)
        self.canvas_view.setMinimumSize(500, 400)
        
        # 创建场景
        self.scene = QGraphicsScene()
        self.canvas_view.setScene(self.scene)
        
        # 设置场景背景
        self.scene.setBackgroundBrush(QBrush(QColor(235, 238, 245)))
        
        layout.addWidget(self.canvas_view)
        
        # 统计信息
        self.stats_label = QLabel("未添加照片")
        self.stats_label.setStyleSheet("font-size: 12px; color: #606266;")
        layout.addWidget(self.stats_label)
        
        return panel
    
    def create_control_panel(self):
        """创建控制面板"""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # 标题
        title = QLabel("排版设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #303133;")
        layout.addWidget(title)
        
        # 画布尺寸设置
        canvas_group = QGroupBox("画布尺寸")
        canvas_layout = QVBoxLayout(canvas_group)
        self.canvas_combo = QComboBox()
        for size in size_manager.canvas_sizes:
            self.canvas_combo.addItem(f"{size['name']}: {size['width']}×{size['height']}cm", size)
        self.canvas_combo.currentIndexChanged.connect(self.update_canvas_size)
        canvas_layout.addWidget(self.canvas_combo)
        layout.addWidget(canvas_group)
        
        # 间距设置
        spacing_group = QGroupBox("照片间距")
        spacing_layout = QGridLayout(spacing_group)
        spacing_layout.addWidget(QLabel("水平间距(cm):"), 0, 0)
        self.h_spacing = QLineEdit("0.3")
        self.h_spacing.textChanged.connect(self.update_preview)
        spacing_layout.addWidget(self.h_spacing, 0, 1)
        spacing_layout.addWidget(QLabel("垂直间距(cm):"), 1, 0)
        self.v_spacing = QLineEdit("0.3")
        self.v_spacing.textChanged.connect(self.update_preview)
        spacing_layout.addWidget(self.v_spacing, 1, 1)
        layout.addWidget(spacing_group)
        
        # DPI设置
        dpi_group = QGroupBox("输出质量")
        dpi_layout = QVBoxLayout(dpi_group)
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["150 DPI (普通)", "300 DPI (标准)", "600 DPI (高质量)", "1200 DPI (超高质量)"])
        self.dpi_combo.setCurrentIndex(1)
        self.dpi_combo.currentIndexChanged.connect(self.update_preview)
        dpi_layout.addWidget(self.dpi_combo)
        layout.addWidget(dpi_group)
        
        # 导出设置
        export_group = QGroupBox("批量导出")
        export_layout = QVBoxLayout(export_group)
        
        # 格式选择
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("导出格式:"))
        self.png_check = QCheckBox("PNG")
        self.png_check.setChecked(True)
        self.jpg_check = QCheckBox("JPG")
        self.bmp_check = QCheckBox("BMP")
        self.tiff_check = QCheckBox("TIFF")
        format_layout.addWidget(self.png_check)
        format_layout.addWidget(self.jpg_check)
        format_layout.addWidget(self.bmp_check)
        format_layout.addWidget(self.tiff_check)
        export_layout.addLayout(format_layout)
        
        # 导出按钮
        self.export_btn = QPushButton("批量导出")
        self.export_btn.clicked.connect(self.batch_export)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #409eff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #66b1ff; }
            QPushButton:disabled { background-color: #c0c4cc; }
        """)
        export_layout.addWidget(self.export_btn)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        export_layout.addWidget(self.progress_bar)
        
        layout.addWidget(export_group)
        
        layout.addStretch()
        
        return panel
    
    def apply_stylesheet(self):
        """应用样式表"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fa;
                font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                border: 1px solid #dcdfe6;
                border-radius: 8px;
                margin-top: 8px;
                font-weight: bold;
                padding: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                font-size: 12px;
                color: #409eff;
            }
            QLabel {
                font-size: 12px;
                color: #606266;
            }
            QComboBox, QLineEdit, QSpinBox {
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
                min-height: 25px;
                background-color: white;
            }
            QComboBox:hover, QLineEdit:hover {
                border-color: #409eff;
            }
            QPushButton {
                background-color: #409eff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
            QPushButton:pressed {
                background-color: #3a8ee6;
            }
            QListWidget {
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                background-color: white;
                padding: 5px;
            }
            QListWidget::item {
                border-bottom: 1px solid #ebeef5;
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #e6f7ff;
            }
            QCheckBox {
                font-size: 12px;
                spacing: 5px;
            }
            QProgressBar {
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                text-align: center;
                background-color: #f5f7fa;
            }
            QProgressBar::chunk {
                background-color: #409eff;
                border-radius: 3px;
            }
            QFrame {
                background-color: white;
                border-radius: 8px;
            }
        """)
    
    def select_photos(self):
        """选择照片文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择照片", "", 
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if files:
            self.add_photos(files)
    
    def add_photos(self, file_paths):
        """添加照片到列表"""
        for file_path in file_paths:
            # 检查是否已存在
            if any(p.file_path == file_path for p in self.photo_sources):
                continue
            
            # 加载图片
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                continue
            
            # 创建PhotoSource对象
            photo_source = PhotoSource(file_path, pixmap)
            self.photo_sources.append(photo_source)
            
            # 添加到列表显示
            item = QListWidgetItem()
            item_widget = PhotoListWidget(photo_source)
            item.setSizeHint(item_widget.sizeHint())
            self.photo_list.addItem(item)
            self.photo_list.setItemWidget(item, item_widget)
        
        self.update_stats()
        self.statusBar.showMessage(f"已添加 {len(file_paths)} 张照片")
    
    def clear_all_photos(self):
        """清空所有照片"""
        if self.photo_sources:
            reply = QMessageBox.question(
                self, "确认", "确定要清空所有照片吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.photo_sources.clear()
                self.photo_list.clear()
                self.scene.clear()
                self.update_stats()
                self.statusBar.showMessage("已清空所有照片")
    
    def update_canvas_size(self, index):
        """更新画布尺寸"""
        self.update_preview()
    
    def update_preview(self):
        """更新预览"""
        # 获取当前画布尺寸
        canvas_data = self.canvas_combo.currentData()
        if not canvas_data:
            return
        
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        
        # 获取DPI
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        
        # 厘米转像素
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        # 设置场景大小
        self.scene.setSceneRect(0, 0, canvas_w_px, canvas_h_px)
        
        # 绘制画布背景
        self.scene.clear()
        
        # 绘制白色背景
        bg = self.scene.addRect(0, 0, canvas_w_px, canvas_h_px, 
                                  QPen(Qt.GlobalColor.transparent), 
                                  QBrush(Qt.GlobalColor.white))
        
        # 绘制边框
        border = self.scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                                     QPen(QColor(180, 190, 210), 3, Qt.PenStyle.DashLine),
                                     QBrush(Qt.GlobalColor.transparent))
        
        # 如果有照片，显示提示
        if not self.photo_sources:
            text = self.scene.addText("请添加照片并点击自动排版")
            text.setDefaultTextColor(QColor(150, 150, 150))
            text.setFont(QFont("Microsoft YaHei", 14))
            text.setPos(canvas_w_px/2 - 100, canvas_h_px/2 - 20)
    
    def auto_layout(self):
        """自动排版"""
        if not self.photo_sources:
            QMessageBox.warning(self, "提示", "请先添加照片！")
            return
        
        # 更新照片参数
        for i in range(self.photo_list.count()):
            item = self.photo_list.item(i)
            widget = self.photo_list.itemWidget(item)
            if widget:
                widget.get_values()
        
        # 获取画布参数
        canvas_data = self.canvas_combo.currentData()
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        # 获取间距
        try:
            h_space = float(self.h_spacing.text())
            v_space = float(self.v_spacing.text())
        except ValueError:
            h_space = v_space = 0.3
        
        spacing_px = int((h_space + v_space) / 2 / 2.54 * dpi)
        
        # 创建后台布局计算线程
        self.layout_worker = LayoutWorker(
            self.photo_sources, canvas_w_px, canvas_h_px, spacing_px
        )
        self.layout_worker.progress.connect(self.on_layout_progress)
        self.layout_worker.finished.connect(self.on_layout_finished)
        self.layout_worker.start()
        
        self.statusBar.showMessage("正在计算排版...")
    
    def on_layout_progress(self, value):
        """布局进度更新"""
        self.statusBar.showMessage(f"正在计算排版... {value}%")
    
    def on_layout_finished(self, layout_items):
        """布局计算完成"""
        # 清除现有项
        self.scene.clear()
        
        # 获取参数
        canvas_data = self.canvas_combo.currentData()
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        # 绘制背景
        self.scene.addRect(0, 0, canvas_w_px, canvas_h_px, 
                           QPen(Qt.GlobalColor.transparent), 
                           QBrush(Qt.GlobalColor.white))
        self.scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                          QPen(QColor(180, 190, 210), 3, Qt.PenStyle.DashLine),
                          QBrush(Qt.GlobalColor.transparent))
        
        # 添加照片项
        total_photos = 0
        for item_data in layout_items:
            source_idx = item_data['source_index']
            if source_idx < len(self.photo_sources):
                photo = self.photo_sources[source_idx]
                size_info = size_manager.photo_sizes[photo.target_size_index]
                
                w_px = int(size_info["width"] / 2.54 * dpi)
                h_px = int(size_info["height"] / 2.54 * dpi)
                
                photo_item = PhotoItem(photo, w_px, h_px)
                photo_item.setPos(item_data['x'], item_data['y'])
                self.scene.addItem(photo_item)
                total_photos += 1
        
        self.statusBar.showMessage(f"排版完成，共 {total_photos} 张照片")
        
        # 更新统计
        self.stats_label.setText(f"画布: {canvas_w_cm}×{canvas_h_cm}cm | 照片: {total_photos}张 | DPI: {dpi}")
    
    def update_stats(self):
        """更新统计信息"""
        count = len(self.photo_sources)
        self.stats_label.setText(f"已添加 {count} 张照片")
    
    def batch_export(self):
        """批量导出"""
        if not self.photo_sources:
            QMessageBox.warning(self, "提示", "没有可导出的照片！")
            return
        
        # 收集选中的格式
        formats = []
        if self.png_check.isChecked():
            formats.append("PNG")
        if self.jpg_check.isChecked():
            formats.append("JPG")
        if self.bmp_check.isChecked():
            formats.append("BMP")
        if self.tiff_check.isChecked():
            formats.append("TIFF")
        
        if not formats:
            QMessageBox.warning(self, "提示", "请至少选择一个导出格式！")
            return
        
        # 选择保存目录
        output_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not output_dir:
            return
        
        # 获取画布参数
        canvas_data = self.canvas_combo.currentData()
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        # 开始导出
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        base_name = "证件照片排版"
        
        self.export_worker = ExportWorker(
            self.scene, canvas_w_px, canvas_h_px, dpi, 
            formats, output_dir, base_name
        )
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()
        
        self.statusBar.showMessage("正在导出...")
    
    def on_export_progress(self, value):
        """导出进度更新"""
        self.progress_bar.setValue(value)
        self.statusBar.showMessage(f"正在导出... {value}%")
    
    def on_export_finished(self, output_dir):
        """导出完成"""
        self.export_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.statusBar.showMessage("导出完成")
        
        QMessageBox.information(
            self, "导出成功", 
            f"照片已导出到:\n{output_dir}"
        )
    
    def on_export_error(self, error_msg):
        """导出错误"""
        self.export_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.statusBar.showMessage("导出失败")
        
        QMessageBox.critical(self, "导出失败", f"导出时发生错误:\n{error_msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EnhancedPhotoLayoutTool()
    window.show()
    sys.exit(app.exec())
