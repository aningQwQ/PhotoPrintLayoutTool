# -*- coding: utf-8 -*-
"""
照片排版工具 - v7.6.3
Copyright (c) 2025 徐英珺
https://github.com/aningQwQ/PhotoPrintLayoutTool
- 修复深色模式照片列表样式不同步
- 修复背景矩形脆弱类型判断
- 添加窗口关闭线程安全处理
- 优化大图内存占用（缩略图+按需加载）
- 修正Guillotine算法裁切线计算逻辑
- 移除深色模式按钮
- 修复深色模式导出照片时背景变黑问题
"""

import sys
import json
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QComboBox, 
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QFileDialog, QLineEdit, QMessageBox,
    QRadioButton, QListWidget,
    QListWidgetItem, QCheckBox, QProgressBar, QSpinBox,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsItem, QStatusBar,
    QSplitter, QFrame,
    QListView, 
)
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QBrush, QFont, QTransform,
    QPalette,
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, QPointF


class PhotoSource:
    """照片数据模型 - 只存储路径和缩略图，原图按需加载"""
    def __init__(self, file_path, thumbnail=None):
        self.id = id(self)
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        # 缩略图（用于列表显示）
        self.thumbnail = thumbnail
        # 原图懒加载缓存
        self._full_pixmap = None
        # 每个照片的排版参数
        self.target_size_index = 0  # 默认使用第一个尺寸
        self.quantity = 1  # 默认数量
        self.fit_mode = "crop"  # "crop"裁切或"stretch"变形
    
    def get_full_pixmap(self):
        """按需加载原图（带缓存）"""
        if self._full_pixmap is None:
            self._full_pixmap = QPixmap(self.file_path)
        return self._full_pixmap
    
    def release_full_pixmap(self):
        """释放原图以节省内存（排版完成后可调用）"""
        self._full_pixmap = None


class PhotoItem(QGraphicsPixmapItem):
    """画布上的照片项，支持拖拽和吸附对齐"""
    def __init__(self, photo_source, width_px, height_px, snap_enabled=True, rotated=False, parent=None):
        super().__init__(parent)
        self.photo_source = photo_source
        self.target_width = width_px
        self.target_height = height_px
        self.snap_enabled = snap_enabled
        self.snap_threshold = 20  # 吸附距离阈值（像素）
        self.rotated = rotated
        
        # 获取原始图像（如果需要旋转），从PhotoSource按需加载
        original = photo_source.get_full_pixmap()
        if rotated:
            original = original.transformed(QTransform().rotate(90))
        
        # 根据fit_mode缩放照片
        if photo_source.fit_mode == "crop":
            # 裁切模式：保持比例，居中放大填充整个区域（无白边）
            # 步骤1：先放大到覆盖整个区域
            scaled = original.scaled(
                width_px, height_px,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # 步骤2：居中裁剪到目标尺寸
            x_offset = (scaled.width() - width_px) // 2 if scaled.width() > width_px else 0
            y_offset = (scaled.height() - height_px) // 2 if scaled.height() > height_px else 0
            
            # 裁剪图像
            if scaled.width() > width_px or scaled.height() > height_px:
                scaled = scaled.copy(x_offset, y_offset, width_px, height_px)
            
            self.setPixmap(scaled)
        else:
            # 变形模式：拉伸到目标尺寸
            scaled = original.scaled(
                width_px, height_px,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)
        
        # 设置项标志
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
    
    def itemChange(self, change, value):
        """处理位置变化，实现吸附功能"""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            pass
        return super().itemChange(change, value)

    def set_snap_enabled(self, enabled):
        """设置是否启用吸附功能"""
        self.snap_enabled = enabled


class SnapPhotoItem(PhotoItem):
    """支持吸附功能的照片项，改进版支持多尺寸混合排版"""
    def __init__(self, photo_source, width_px, height_px, snap_enabled=True, rotated=False, parent=None):
        super().__init__(photo_source, width_px, height_px, snap_enabled, rotated, parent)
        
    def itemChange(self, change, value):
        """处理位置变化，实现吸附功能"""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self.snap_enabled and self.scene():
                return self.calculate_snap_position(value)
        return super().itemChange(change, value)
    
    def calculate_snap_position(self, new_pos):
        """计算吸附后的位置，支持多尺寸混合排版"""
        if not new_pos:
            return new_pos
            
        rect = self.sceneBoundingRect()
        
        # 获取画布边界
        scene_rect = self.scene().sceneRect()
        
        # 初始化吸附位置为当前位置
        snapped_x = new_pos.x()
        snapped_y = new_pos.y()
        
        # 记录是否已经有X轴和Y轴的吸附
        x_snapped = False
        y_snapped = False
        
        # ====== 1. 画布边缘吸附 ======
        # 左边缘
        if abs(new_pos.x() - scene_rect.left()) < self.snap_threshold:
            snapped_x = scene_rect.left()
            x_snapped = True
        # 右边缘
        elif abs(new_pos.x() + rect.width() - scene_rect.right()) < self.snap_threshold:
            snapped_x = scene_rect.right() - rect.width()
            x_snapped = True
        # 上边缘
        if abs(new_pos.y() - scene_rect.top()) < self.snap_threshold:
            snapped_y = scene_rect.top()
            y_snapped = True
        # 下边缘
        elif abs(new_pos.y() + rect.height() - scene_rect.bottom()) < self.snap_threshold:
            snapped_y = scene_rect.bottom() - rect.height()
            y_snapped = True
        
        # ====== 2. 画布中心线吸附 ======
        if not x_snapped:
            center_x_canvas = scene_rect.left() + scene_rect.width() / 2
            current_center_x = new_pos.x() + rect.width() / 2
            if abs(current_center_x - center_x_canvas) < self.snap_threshold:
                snapped_x = center_x_canvas - rect.width() / 2
                x_snapped = True
        
        if not y_snapped:
            center_y_canvas = scene_rect.top() + scene_rect.height() / 2
            current_center_y = new_pos.y() + rect.height() / 2
            if abs(current_center_y - center_y_canvas) < self.snap_threshold:
                snapped_y = center_y_canvas - rect.height() / 2
                y_snapped = True
        
        # ====== 3. 其他照片边缘吸附（支持多尺寸混合排版）======
        items = self.scene().items()
        for item in items:
            if item == self or not isinstance(item, QGraphicsPixmapItem):
                continue
            
            item_rect = item.sceneBoundingRect()
            
            # --- X轴边缘吸附 ---
            if not x_snapped:
                # 左边对右边（当前照片左边 -> 其他照片右边）
                if abs(new_pos.x() - item_rect.right()) < self.snap_threshold:
                    snapped_x = item_rect.right()
                    x_snapped = True
                # 右边对左边（当前照片右边 -> 其他照片左边）
                elif abs(new_pos.x() + rect.width() - item_rect.left()) < self.snap_threshold:
                    snapped_x = item_rect.left() - rect.width()
                    x_snapped = True
                # 左对左
                elif abs(new_pos.x() - item_rect.left()) < self.snap_threshold:
                    snapped_x = item_rect.left()
                    x_snapped = True
                # 右对右
                elif abs(new_pos.x() + rect.width() - item_rect.right()) < self.snap_threshold:
                    snapped_x = item_rect.right() - rect.width()
                    x_snapped = True
            
            # --- Y轴边缘吸附 ---
            if not y_snapped:
                # 上边对下边
                if abs(new_pos.y() - item_rect.bottom()) < self.snap_threshold:
                    snapped_y = item_rect.bottom()
                    y_snapped = True
                # 下边对上边
                elif abs(new_pos.y() + rect.height() - item_rect.left()) < self.snap_threshold:
                    snapped_y = item_rect.left() - rect.height()
                    y_snapped = True
                # 上对上
                elif abs(new_pos.y() - item_rect.top()) < self.snap_threshold:
                    snapped_y = item_rect.top()
                    y_snapped = True
                # 下对下
                elif abs(new_pos.y() + rect.height() - item_rect.bottom()) < self.snap_threshold:
                    snapped_y = item_rect.bottom() - rect.height()
                    y_snapped = True
            
            # --- 中心对齐吸附 ---
            if not x_snapped:
                center_x = new_pos.x() + rect.width() / 2
                if abs(center_x - item_rect.center().x()) < self.snap_threshold:
                    snapped_x = item_rect.center().x() - rect.width() / 2
                    x_snapped = True
            
            if not y_snapped:
                center_y = new_pos.y() + rect.height() / 2
                if abs(center_y - item_rect.center().y()) < self.snap_threshold:
                    snapped_y = item_rect.center().y() - rect.height() / 2
                    y_snapped = True
            
            # --- 对角吸附（角落对齐）---
            # 左上角对齐
            if not x_snapped and not y_snapped:
                if (abs(new_pos.x() - item_rect.left()) < self.snap_threshold and 
                    abs(new_pos.y() - item_rect.top()) < self.snap_threshold):
                    snapped_x = item_rect.left()
                    snapped_y = item_rect.top()
                    x_snapped = True
                    y_snapped = True
                # 右上角对齐
                elif (abs(new_pos.x() + rect.width() - item_rect.right()) < self.snap_threshold and 
                      abs(new_pos.y() - item_rect.top()) < self.snap_threshold):
                    snapped_x = item_rect.right() - rect.width()
                    snapped_y = item_rect.top()
                    x_snapped = True
                    y_snapped = True
                # 左下角对齐
                elif (abs(new_pos.x() - item_rect.left()) < self.snap_threshold and 
                      abs(new_pos.y() + rect.height() - item_rect.bottom()) < self.snap_threshold):
                    snapped_x = item_rect.left()
                    snapped_y = item_rect.bottom() - rect.height()
                    x_snapped = True
                    y_snapped = True
                # 右下角对齐
                elif (abs(new_pos.x() + rect.width() - item_rect.right()) < self.snap_threshold and 
                      abs(new_pos.y() + rect.height() - item_rect.bottom()) < self.snap_threshold):
                    snapped_x = item_rect.right() - rect.width()
                    snapped_y = item_rect.bottom() - rect.height()
                    x_snapped = True
                    y_snapped = True
            
            # --- 阶梯式边缘吸附（混合排版专用）---
            # 当照片在另一个照片旁边但稍微错开时
            if not x_snapped:
                # 左边在另一个照片宽度范围内
                if (item_rect.left() <= new_pos.x() <= item_rect.right() and
                    abs(new_pos.y() - item_rect.top()) < self.snap_threshold):
                    snapped_y = item_rect.top()
                    y_snapped = True
                elif (item_rect.left() <= new_pos.x() <= item_rect.right() and
                      abs(new_pos.y() + rect.height() - item_rect.bottom()) < self.snap_threshold):
                    snapped_y = item_rect.bottom() - rect.height()
                    y_snapped = True
        
        return QPointF(snapped_x, snapped_y)


class LayoutWorker(QThread):
    """后台布局计算线程，支持多页和Guillotine算法"""
    progress = Signal(int)
    finished = Signal(list)  # 返回多页布局列表
    
    def __init__(self, photo_sources, canvas_width, canvas_height, h_spacing_px, v_spacing_px, dpi=300, left_margin=0, top_margin=0, guillotine_mode=True):
        super().__init__()
        self.photo_sources = photo_sources
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.h_spacing_px = h_spacing_px
        self.v_spacing_px = v_spacing_px
        self.dpi = dpi
        self.left_margin = left_margin
        self.top_margin = top_margin
        self.guillotine_mode = guillotine_mode
    
    def run(self):
        """执行布局计算，支持多页和Guillotine算法"""
        pages = []  # 存储每一页的布局
        
        # 收集所有需要排列的矩形
        rects = []
        for i, photo in enumerate(self.photo_sources):
            size_info = size_manager.get_photo_size(photo.target_size_index)
            if size_info:
                w = size_info["width"]
                h = size_info["height"]
                w_px = self.cm_to_px(w)
                h_px = self.cm_to_px(h)
                
                for q in range(photo.quantity):
                    # 存储 (含间距宽度, 含间距高度, 照片索引, 副本序号)
                    rects.append((w_px + self.h_spacing_px, h_px + self.v_spacing_px, i, q))
            
            self.progress.emit(int((i + 1) / max(len(self.photo_sources), 1) * 30))
        
        if not rects:
            self.finished.emit([])
            return
        
        if self.guillotine_mode:
            # 使用Guillotine算法
            pages = self.guillotine_packing(rects)
        else:
            # 使用原来的贪心算法
            pages = self.greedy_packing(rects)
        
        self.progress.emit(100)
        # 排版完成后，释放所有照片的原图以节省内存
        for photo in self.photo_sources:
            photo.release_full_pixmap()
        self.finished.emit(pages)
    
    def guillotine_packing(self, rects):
        """Guillotine断头台装箱算法 - 支持旋转
        返回页面列表，每个页面包含照片布局和裁切线信息
        """
        pages = []
        page_cut_lines = []  # 当前页的裁切线
        current_page = []

        # Guillotine可用空间列表，每个空间为 (x, y, width, height) 单位为像素（含安全边距）
        spaces = [(self.left_margin, self.top_margin, self.canvas_width, self.canvas_height)]

        # 按高度降序排序，优先放置大照片
        rects = sorted(rects, key=lambda x: x[1], reverse=True)

        # 安全限制：防止无限循环
        max_iterations = len(rects) * 10
        iteration_count = 0
        skipped_count = 0

        for idx, rect in enumerate(rects):
            iteration_count += 1
            if iteration_count > max_iterations:
                break

            # rect = (slot_w, slot_h, source_idx, quantity_idx)
            slot_w, slot_h, source_idx, quantity_idx = rect
            best_space = None
            best_idx = -1
            rotated = False

            # 寻找最佳放置位置（考虑旋转）
            for i, space in enumerate(spaces):
                # 尝试不旋转
                if space[2] >= slot_w and space[3] >= slot_h:
                    best_space = space
                    best_idx = i
                    rotated = False
                    break
                # 尝试旋转（宽高互换）
                if space[2] >= slot_h and space[3] >= slot_w:
                    best_space = space
                    best_idx = i
                    rotated = True
                    break

            if best_space:
                skipped_count = 0
                # 确定实际占位尺寸（含间距）
                if rotated:
                    actual_slot_w = slot_h
                    actual_slot_h = slot_w
                else:
                    actual_slot_w = slot_w
                    actual_slot_h = slot_h
                
                # 照片净尺寸（不含间距）
                photo_w = actual_slot_w - self.h_spacing_px
                photo_h = actual_slot_h - self.v_spacing_px
                
                current_page.append({
                    'x': best_space[0],
                    'y': best_space[1],
                    'width': photo_w,
                    'height': photo_h,
                    'source_index': source_idx,
                    'rotation': rotated
                })

                # 记录裁切线（使用含间距的占位尺寸）
                # 水平裁切线在照片底部（含间距）
                page_cut_lines.append({
                    'x1': best_space[0],
                    'y1': best_space[1] + actual_slot_h,
                    'x2': best_space[0] + best_space[2],
                    'y2': best_space[1] + actual_slot_h,
                    'type': 'horizontal'
                })
                # 垂直裁切线在照片右侧（含间距）
                page_cut_lines.append({
                    'x1': best_space[0] + actual_slot_w,
                    'y1': best_space[1],
                    'x2': best_space[0] + actual_slot_w,
                    'y2': best_space[1] + best_space[3],
                    'type': 'vertical'
                })
                
                # 更新Guillotine空间：使用BSSF（最佳短边优先）策略
                right_w = best_space[2] - actual_slot_w
                right_h = best_space[3]
                bottom_w = actual_slot_w
                bottom_h = best_space[3] - actual_slot_h
                
                new_spaces = []
                for i, s in enumerate(spaces):
                    if i == best_idx:
                        # 添加右侧剩余空间（如果足够大）
                        if right_w > 10 and right_h > 10:
                            new_spaces.append((best_space[0] + actual_slot_w, best_space[1], right_w, right_h))
                        # 添加底部剩余空间
                        if bottom_w > 10 and bottom_h > 10:
                            new_spaces.append((best_space[0], best_space[1] + actual_slot_h, bottom_w, bottom_h))
                    else:
                        new_spaces.append(s)
                spaces = new_spaces
                
                self.progress.emit(50 + int(len(current_page) / len(rects) * 40))
            else:
                # 当前页放不下，创建新页
                if current_page:
                    pages.append({
                        'items': current_page,
                        'cut_lines': page_cut_lines.copy()
                    })
                current_page = []
                page_cut_lines = []
                spaces = [(self.left_margin, self.top_margin, self.canvas_width, self.canvas_height)]
                
                # 尝试放在新页上（也需要考虑旋转）
                placed = False
                for i, space in enumerate(spaces):
                    if space[2] >= slot_w and space[3] >= slot_h:
                        actual_slot_w = slot_w
                        actual_slot_h = slot_h
                        rotated = False
                        placed = True
                    elif space[2] >= slot_h and space[3] >= slot_w:
                        actual_slot_w = slot_h
                        actual_slot_h = slot_w
                        rotated = True
                        placed = True
                    else:
                        continue
                    
                    photo_w = actual_slot_w - self.h_spacing_px
                    photo_h = actual_slot_h - self.v_spacing_px
                    current_page.append({
                        'x': space[0],
                        'y': space[1],
                        'width': photo_w,
                        'height': photo_h,
                        'source_index': source_idx,
                        'rotation': rotated
                    })
                    
                    # 添加裁切线
                    page_cut_lines.append({
                        'x1': space[0],
                        'y1': space[1] + actual_slot_h,
                        'x2': space[0] + space[2],
                        'y2': space[1] + actual_slot_h,
                        'type': 'horizontal'
                    })
                    page_cut_lines.append({
                        'x1': space[0] + actual_slot_w,
                        'y1': space[1],
                        'x2': space[0] + actual_slot_w,
                        'y2': space[1] + space[3],
                        'type': 'vertical'
                    })
                    
                    # 更新空间
                    right_w = space[2] - actual_slot_w
                    right_h = space[3]
                    bottom_w = actual_slot_w
                    bottom_h = space[3] - actual_slot_h
                    spaces = []
                    if right_w > 10 and right_h > 10:
                        spaces.append((space[0] + actual_slot_w, space[1], right_w, right_h))
                    if bottom_w > 10 and bottom_h > 10:
                        spaces.append((space[0], space[1] + actual_slot_h, bottom_w, bottom_h))
                    break
                
                if not placed:
                    skipped_count += 1
                    if skipped_count > 20:
                        break
                    continue
                else:
                    skipped_count = 0
        
        # 添加最后一页
        if current_page:
            pages.append({
                'items': current_page,
                'cut_lines': page_cut_lines
            })
        
        return pages
    
    def greedy_packing(self, rects):
        """原来的贪心算法（不支持旋转，保留原逻辑）"""
        pages = []
        current_page = []
        cut_lines = []

        rects = sorted(rects, key=lambda x: x[1], reverse=True)

        max_iterations = len(rects) * 10
        iteration_count = 0
        skipped_count = 0

        spaces = [(self.left_margin, self.top_margin, self.canvas_width, self.canvas_height)]

        for rect in rects:
            iteration_count += 1
            if iteration_count > max_iterations:
                break

            slot_w, slot_h, source_idx, quantity_idx = rect
            best_space = None
            best_area = float('inf')
            best_idx = -1

            for i, space in enumerate(spaces):
                if space[2] >= slot_w and space[3] >= slot_h:
                    remaining = (space[2] - slot_w) * (space[3] - slot_h)
                    if remaining < best_area:
                        best_area = remaining
                        best_space = space
                        best_idx = i

            if best_space:
                skipped_count = 0
                photo_w = slot_w - self.h_spacing_px
                photo_h = slot_h - self.v_spacing_px
                current_page.append({
                    'x': best_space[0],
                    'y': best_space[1],
                    'width': photo_w,
                    'height': photo_h,
                    'source_index': source_idx,
                    'rotation': False
                })
                
                new_spaces = []
                for i, s in enumerate(spaces):
                    if i == best_idx:
                        right_space = (best_space[0] + slot_w, best_space[1], best_space[2] - slot_w, best_space[3])
                        bottom_space = (best_space[0], best_space[1] + slot_h, slot_w, best_space[3] - slot_h)
                        if right_space[2] > 10 and right_space[3] > 10:
                            new_spaces.append(right_space)
                        if bottom_space[2] > 10 and bottom_space[3] > 10:
                            new_spaces.append(bottom_space)
                    else:
                        new_spaces.append(s)
                spaces = new_spaces
                
                self.progress.emit(50 + int(len(current_page) / len(rects) * 40))
            else:
                if current_page:
                    pages.append({
                        'items': current_page,
                        'cut_lines': cut_lines.copy()
                    })
                current_page = []
                cut_lines = []
                spaces = [(self.left_margin, self.top_margin, self.canvas_width, self.canvas_height)]
                
                placed = False
                for i, space in enumerate(spaces):
                    if space[2] >= slot_w and space[3] >= slot_h:
                        photo_w = slot_w - self.h_spacing_px
                        photo_h = slot_h - self.v_spacing_px
                        current_page.append({
                            'x': space[0],
                            'y': space[1],
                            'width': photo_w,
                            'height': photo_h,
                            'source_index': source_idx,
                            'rotation': False
                        })
                        right_w = space[2] - slot_w
                        right_h = space[3]
                        bottom_w = slot_w
                        bottom_h = space[3] - slot_h
                        spaces = []
                        if right_w > 10 and right_h > 10:
                            spaces.append((space[0] + slot_w, space[1], right_w, right_h))
                        if bottom_w > 10 and bottom_h > 10:
                            spaces.append((space[0], space[1] + slot_h, bottom_w, bottom_h))
                        placed = True
                        break
                
                if not placed:
                    skipped_count += 1
                    if skipped_count > 20:
                        break
                    continue
                else:
                    skipped_count = 0
        
        if current_page:
            pages.append({
                'items': current_page,
                'cut_lines': cut_lines
            })
        
        return pages
    
    def cm_to_px(self, cm):
        """厘米转像素"""
        inches = cm / 2.54
        return int(inches * self.dpi)


class ExportWorker(QThread):
    """后台导出线程"""
    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, scenes, canvas_width, canvas_height, dpi, formats, output_dir, base_name):
        super().__init__()
        self.scenes = scenes
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.dpi = dpi
        self.formats = formats
        self.output_dir = output_dir
        self.base_name = base_name
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
    
    def run(self):
        try:
            total = len(self.scenes) * len(self.formats)
            current = 0
            
            for page_idx, scene in enumerate(self.scenes):
                if self._is_cancelled:
                    break
                for fmt in self.formats:
                    if self._is_cancelled:
                        break
                    img = QImage(self.canvas_width, self.canvas_height, QImage.Format.Format_RGB32)
                    img.fill(Qt.GlobalColor.white)
                    
                    painter = QPainter(img)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    
                    scene.render(painter)
                    painter.end()
                    
                    ext = fmt.lower()
                    if len(self.scenes) > 1:
                        file_path = os.path.join(self.output_dir, f"{self.base_name}_第{page_idx+1}页.{ext}")
                    else:
                        file_path = os.path.join(self.output_dir, f"{self.base_name}.{ext}")
                    
                    if ext == "jpg" or ext == "jpeg":
                        img.save(file_path, fmt, 95)
                    else:
                        img.save(file_path, fmt)
                    
                    current += 1
                    self.progress.emit(int(current / total * 100))
            
            if self._is_cancelled:
                self.error.emit("导出已被取消")
            else:
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
            except:
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
        except:
            return False
    
    def get_photo_size(self, index):
        if 0 <= index < len(self.photo_sizes):
            return self.photo_sizes[index]
        return None
    
    def get_canvas_size(self, index):
        if 0 <= index < len(self.canvas_sizes):
            return self.canvas_sizes[index]
        return None


size_manager = SizeManager()


class PhotoListWidget(QListWidget):
    """支持拖拽的照片列表组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.photo_sources = []
        self.main_window = None
        
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setSpacing(2)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
    
    def set_main_window(self, main_window):
        self.main_window = main_window
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dragLeaveEvent(self, event):
        pass
    
    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                files.append(file_path)
        
        if files and self.main_window:
            self.main_window.add_photos(files)


class PhotoItemWidget(QWidget):
    """照片列表项的自定义组件"""
    delete_requested = Signal(object)
    
    def __init__(self, photo_source, parent=None):
        super().__init__(parent)
        self.photo_source = photo_source
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        
        # 缩略图
        thumbnail_label = QLabel()
        if self.photo_source.thumbnail:
            thumb = self.photo_source.thumbnail
        else:
            thumb = QPixmap(self.photo_source.file_path).scaled(
                50, 50, Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.photo_source.thumbnail = thumb
        thumbnail_label.setPixmap(thumb)
        thumbnail_label.setFixedSize(50, 50)
        thumbnail_label.setStyleSheet("border: 1px solid palette(mid); border-radius: 4px;")
        layout.addWidget(thumbnail_label)
        
        # 信息区域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        name_label = QLabel(self.photo_source.file_name)
        name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        name_label.setToolTip(self.photo_source.file_path)
        name_label.setMaximumWidth(130)
        name_label.setWordWrap(True)
        info_layout.addWidget(name_label)
        
        # 设置行
        row1 = QHBoxLayout()
        row1.setSpacing(5)
        
        self.size_combo = QComboBox()
        for size in size_manager.photo_sizes:
            self.size_combo.addItem(f"{size['name']}", size)
        self.size_combo.setCurrentIndex(self.photo_source.target_size_index)
        self.size_combo.setFixedWidth(70)
        row1.addWidget(self.size_combo)
        
        qty_label = QLabel("数量:")
        qty_label.setStyleSheet("font-size: 10px;")
        row1.addWidget(qty_label)
        
        self.qty_spin = QSpinBox()
        self.qty_spin.setMinimum(1)
        self.qty_spin.setMaximum(100)
        self.qty_spin.setValue(self.photo_source.quantity)
        self.qty_spin.setFixedWidth(40)
        self.qty_spin.setStyleSheet("QSpinBox { font-size: 10px; min-height: 20px; }")
        row1.addWidget(self.qty_spin)
        
        info_layout.addLayout(row1)
        
        # 适应模式选择
        row2 = QHBoxLayout()
        row2.setSpacing(5)
        
        self.crop_radio = QRadioButton("裁切")
        self.crop_radio.setStyleSheet("font-size: 10px;")
        self.crop_radio.setChecked(self.photo_source.fit_mode == "crop")
        
        self.stretch_radio = QRadioButton("变形")
        self.stretch_radio.setStyleSheet("font-size: 10px;")
        self.stretch_radio.setChecked(self.photo_source.fit_mode == "stretch")
        
        row2.addWidget(self.crop_radio)
        row2.addWidget(self.stretch_radio)
        row2.addStretch()
        
        info_layout.addLayout(row2)
        
        layout.addLayout(info_layout)
        
        # 删除按钮
        self.delete_btn = QPushButton("×")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f56c6c;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f78989;
            }
        """)
        self.delete_btn.setToolTip("删除此照片")
        self.delete_btn.clicked.connect(self.on_delete_clicked)
        layout.addWidget(self.delete_btn)
        
        self.setMinimumHeight(70)
        self.setMaximumHeight(80)
    
    def on_delete_clicked(self):
        reply = QMessageBox.question(
            self, 
            "确认删除", 
            f"确定要删除照片「{self.photo_source.file_name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.photo_source)
    
    def get_values(self):
        self.photo_source.target_size_index = self.size_combo.currentIndex()
        self.photo_source.quantity = self.qty_spin.value()
        if self.crop_radio.isChecked():
            self.photo_source.fit_mode = "crop"
        else:
            self.photo_source.fit_mode = "stretch"
        return self.photo_source


class ZoomableGraphicsView(QGraphicsView):
    """支持缩放的GraphicsView"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_factor = 1.0
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(50, 50, 50)))
        self.setStyleSheet("border: none;")
    
    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        if event.angleDelta().y() > 0:
            self.zoom_factor *= zoom_in_factor
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.zoom_factor *= zoom_out_factor
            self.scale(zoom_out_factor, zoom_out_factor)
        
        self.zoom_factor = max(0.1, min(self.zoom_factor, 5.0))
    
    def zoom_to_fit(self):
        self.zoom_factor = 1.0
        self.resetTransform()
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class EnhancedPhotoLayoutTool(QMainWindow):
    THEME = {
        "light": {
            "window_bg": "#f5f7fa",
            "panel_bg": "#ffffff",
            "border": "#dcdfe6",
            "border_light": "#ebeef5",
            "text_primary": "#303133",
            "text_regular": "#606266",
            "text_secondary": "#909399",
            "text_placeholder": "#c0c4cc",
            "accent": "#409eff",
            "accent_hover": "#66b1ff",
            "success": "#67c23a",
            "success_hover": "#85ce61",
            "warning": "#e6a23c",
            "warning_hover": "#ebb563",
            "danger": "#f56c6c",
            "danger_hover": "#f78989",
            "disabled": "#c0c4cc",
            "hover_bg": "#f5f7fa",
            "selected_bg": "#e6f7ff",
            "scene_bg": "#ffffff",
            "view_bg": "#323232",
            "safe_margin_pen": QColor(255, 200, 200, 180),
            "safe_margin_brush": QColor(255, 240, 240, 80),
            "border_pen": QColor(180, 190, 210),
        },
        "dark": {
            "window_bg": "#1e1e1e",
            "panel_bg": "#252526",
            "border": "#3c3c3c",
            "border_light": "#333333",
            "text_primary": "#e0e0e0",
            "text_regular": "#cccccc",
            "text_secondary": "#888888",
            "text_placeholder": "#555555",
            "accent": "#4fc3f7",
            "accent_hover": "#81d4fa",
            "success": "#66bb6a",
            "success_hover": "#81c784",
            "warning": "#ffa726",
            "warning_hover": "#ffb74d",
            "danger": "#ef5350",
            "danger_hover": "#e57373",
            "disabled": "#555555",
            "hover_bg": "#2a2d2e",
            "selected_bg": "#264f78",
            "scene_bg": "#2d2d2d",
            "view_bg": "#1a1a1a",
            "safe_margin_pen": QColor(255, 100, 100, 120),
            "safe_margin_brush": QColor(255, 80, 80, 30),
            "border_pen": QColor(80, 90, 110),
        }
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("证件照片排版工具v7.6.3")
        self.setGeometry(100, 100, 1300, 850)
        
        self.photo_sources = []
        self.layout_worker = None
        self.export_worker = None
        self.page_scenes = []
        self.current_page = 0
        self.snap_enabled = True
        self.dark_mode = self._detect_system_dark_mode()
        
        self.init_ui()
        self.apply_stylesheet()
    
    @staticmethod
    def _detect_system_dark_mode():
        try:
            app = QApplication.instance()
            if app is None:
                return False
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = 0.299 * window_color.red() + 0.587 * window_color.green() + 0.114 * window_color.blue()
            return brightness < 128
        except Exception:
            return False
    
    def init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_panel = self.create_photo_manager_panel()
        splitter.addWidget(left_panel)
        
        center_panel = self.create_canvas_panel()
        splitter.addWidget(center_panel)
        
        right_panel = self.create_control_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        
        self.setCentralWidget(splitter)
        
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪 - 拖拽照片到左侧列表或点击添加按钮")
    
    def create_photo_manager_panel(self):
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        title = QLabel("照片管理")
        title.setObjectName("photoManagerTitle")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        toolbar = QHBoxLayout()
        
        add_btn = QPushButton("添加照片")
        add_btn.setObjectName("addPhotoBtn")
        add_btn.clicked.connect(self.select_photos)
        add_btn.setStyleSheet("""
            QPushButton { background-color: #409eff; color: white; border: none;
                        border-radius: 4px; padding: 6px 12px; font-size: 12px; }
            QPushButton:hover { background-color: #66b1ff; }
        """)
        toolbar.addWidget(add_btn)
        
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("clearPhotosBtn")
        clear_btn.clicked.connect(self.clear_all_photos)
        clear_btn.setStyleSheet("""
            QPushButton { background-color: #f56c6c; color: white; border: none;
                        border-radius: 4px; padding: 6px 12px; font-size: 12px; }
            QPushButton:hover { background-color: #f78989; }
        """)
        toolbar.addWidget(clear_btn)
        
        layout.addLayout(toolbar)
        
        hint = QLabel("提示: 拖拽照片到下方列表，或点击添加按钮")
        hint.setObjectName("photoHint")
        hint.setStyleSheet("font-size: 10px; padding: 3px;")
        layout.addWidget(hint)
        
        self.photo_list = PhotoListWidget()
        self.photo_list.set_main_window(self)
        layout.addWidget(self.photo_list)
        
        self.photo_count_label = QLabel("共 0 张照片")
        self.photo_count_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.photo_count_label)
        
        return panel
    
    def create_canvas_panel(self):
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        header = QHBoxLayout()
        
        title = QLabel("排版预览")
        title.setObjectName("canvasTitle")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        
        zoom_fit_btn = QPushButton("适应窗口")
        zoom_fit_btn.setObjectName("zoomFitBtn")
        zoom_fit_btn.clicked.connect(self.zoom_to_fit)
        header.addWidget(zoom_fit_btn)
        
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setObjectName("zoomInBtn")
        zoom_in_btn.setFixedWidth(30)
        zoom_in_btn.clicked.connect(self.zoom_in)
        header.addWidget(zoom_in_btn)
        
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setObjectName("zoomOutBtn")
        zoom_out_btn.setFixedWidth(30)
        zoom_out_btn.clicked.connect(self.zoom_out)
        header.addWidget(zoom_out_btn)
        
        self.page_label = QLabel("第 1 页")
        self.page_label.setObjectName("pageLabel")
        self.page_label.setStyleSheet("font-size: 12px; margin-left: 20px;")
        header.addWidget(self.page_label)
        
        self.prev_page_btn = QPushButton("上一页")
        self.prev_page_btn.setObjectName("prevPageBtn")
        self.prev_page_btn.clicked.connect(self.prev_page)
        self.prev_page_btn.setEnabled(False)
        header.addWidget(self.prev_page_btn)
        
        self.next_page_btn = QPushButton("下一页")
        self.next_page_btn.setObjectName("nextPageBtn")
        self.next_page_btn.clicked.connect(self.next_page)
        self.next_page_btn.setEnabled(False)
        header.addWidget(self.next_page_btn)
        
        self.snap_checkbox = QCheckBox("吸附对齐")
        self.snap_checkbox.setObjectName("snapCheckbox")
        self.snap_checkbox.setChecked(True)
        self.snap_checkbox.stateChanged.connect(self.on_snap_changed)
        header.addWidget(self.snap_checkbox)
        
        header.addStretch()
        
        auto_layout_btn = QPushButton("自动排版")
        auto_layout_btn.setObjectName("autoLayoutBtn")
        auto_layout_btn.clicked.connect(self.auto_layout)
        header.addWidget(auto_layout_btn)
        
        layout.addLayout(header)
        
        self.canvas_view = ZoomableGraphicsView()
        self.canvas_view.setMinimumSize(500, 400)
        
        self.scene = QGraphicsScene()
        self.canvas_view.setScene(self.scene)
        
        layout.addWidget(self.canvas_view)
        
        self.stats_label = QLabel("未添加照片")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.stats_label)
        
        return panel
    
    def create_control_panel(self):
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        
        title_layout = QHBoxLayout()
        title = QLabel("排版设置")
        title.setObjectName("panelTitle")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #303133;")
        title_layout.addWidget(title)

        license_label = QLabel("Copyright © 2025 徐英珺")
        license_label.setObjectName("copyrightLabel")
        license_label.setStyleSheet("font-size: 10px; color: #909399;")
        title_layout.addWidget(license_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        canvas_group = QGroupBox("画布尺寸")
        canvas_layout = QVBoxLayout(canvas_group)
        self.canvas_combo = QComboBox()
        for size in size_manager.canvas_sizes:
            self.canvas_combo.addItem(f"{size['name']}: {size['width']}×{size['height']}cm", size)
        self.canvas_combo.currentIndexChanged.connect(self.update_canvas_size)
        canvas_layout.addWidget(self.canvas_combo)
        layout.addWidget(canvas_group)
        
        spacing_group = QGroupBox("照片间距 (cm)")
        spacing_layout = QGridLayout(spacing_group)
        spacing_layout.addWidget(QLabel("水平:"), 0, 0)
        self.h_spacing = QLineEdit("0.2")
        self.h_spacing.textChanged.connect(self.update_preview)
        spacing_layout.addWidget(self.h_spacing, 0, 1)
        spacing_layout.addWidget(QLabel("垂直:"), 1, 0)
        self.v_spacing = QLineEdit("0.2")
        self.v_spacing.textChanged.connect(self.update_preview)
        spacing_layout.addWidget(self.v_spacing, 1, 1)
        layout.addWidget(spacing_group)
        
        guillotine_group = QGroupBox("排版模式")
        guillotine_layout = QVBoxLayout(guillotine_group)
        
        self.guillotine_check = QCheckBox("切纸刀模式")
        self.guillotine_check.setChecked(True)
        self.guillotine_check.setToolTip("启用Guillotine算法，方便使用切纸刀")
        self.guillotine_check.setStyleSheet("""
            QCheckBox { font-size: 12px; font-weight: bold; color: #303133; }
            QCheckBox::indicator { width: 18px; height: 18px; }
        """)
        guillotine_layout.addWidget(self.guillotine_check)
        
        guillotine_hint = QLabel("启用Guillotine算法，方便使用切纸刀")
        guillotine_hint.setStyleSheet("font-size: 9px; color: #909399; padding-left: 20px;")
        guillotine_layout.addWidget(guillotine_hint)
        
        layout.addWidget(guillotine_group)
        
        dpi_group = QGroupBox("输出质量")
        dpi_layout = QVBoxLayout(dpi_group)
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["150 DPI", "300 DPI", "600 DPI", "1200 DPI"])
        self.dpi_combo.setCurrentIndex(1)
        self.dpi_combo.currentIndexChanged.connect(self.update_preview)
        dpi_layout.addWidget(self.dpi_combo)
        layout.addWidget(dpi_group)
        
        margin_group = QGroupBox("安全边距 (防止打印裁切)")
        margin_layout = QGridLayout(margin_group)
        margin_layout.addWidget(QLabel("左:"), 0, 0)
        self.left_margin = QLineEdit("0.3")
        self.left_margin.textChanged.connect(self.update_preview)
        margin_layout.addWidget(self.left_margin, 0, 1)
        margin_layout.addWidget(QLabel("cm"), 0, 2)
        
        margin_layout.addWidget(QLabel("右:"), 0, 3)
        self.right_margin = QLineEdit("0.3")
        self.right_margin.textChanged.connect(self.update_preview)
        margin_layout.addWidget(self.right_margin, 0, 4)
        margin_layout.addWidget(QLabel("cm"), 0, 5)
        
        margin_layout.addWidget(QLabel("上:"), 1, 0)
        self.top_margin = QLineEdit("0.3")
        self.top_margin.textChanged.connect(self.update_preview)
        margin_layout.addWidget(self.top_margin, 1, 1)
        margin_layout.addWidget(QLabel("cm"), 1, 2)
        
        margin_layout.addWidget(QLabel("下:"), 1, 3)
        self.bottom_margin = QLineEdit("0.3")
        self.bottom_margin.textChanged.connect(self.update_preview)
        margin_layout.addWidget(self.bottom_margin, 1, 4)
        margin_layout.addWidget(QLabel("cm"), 1, 5)
        
        margin_hint = QLabel("建议: 0.2-0.5cm，防止照片被裁切")
        margin_hint.setStyleSheet("font-size: 9px; color: #909399;")
        margin_layout.addWidget(margin_hint, 2, 0, 1, 6)
        
        layout.addWidget(margin_group)
        
        export_group = QGroupBox("批量导出")
        export_layout = QVBoxLayout(export_group)
        
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("格式:"))
        self.png_check = QCheckBox("PNG")
        self.png_check.setChecked(True)
        self.jpg_check = QCheckBox("JPG")
        self.bmp_check = QCheckBox("BMP")
        self.tiff_check = QCheckBox("TIFF")
        format_layout.addWidget(self.png_check)
        format_layout.addWidget(self.jpg_check)
        format_layout.addWidget(self.bmp_check)
        format_layout.addWidget(self.tiff_check)
        format_layout.addStretch()
        export_layout.addLayout(format_layout)
        
        self.export_btn = QPushButton("批量导出")
        self.export_btn.clicked.connect(self.batch_export)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #409eff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #66b1ff; }
            QPushButton:disabled { background-color: #c0c4cc; }
        """)
        export_layout.addWidget(self.export_btn)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
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
        """)
        export_layout.addWidget(self.progress_bar)
        
        layout.addWidget(export_group)
        
        layout.addStretch()
        
        return panel
    
    def refresh_photo_list_styles(self):
        """刷新照片列表项样式，用于深色模式切换"""
        t = self.THEME["dark" if self.dark_mode else "light"]
        for i in range(self.photo_list.count()):
            widget = self.photo_list.itemWidget(self.photo_list.item(i))
            if widget:
                # 重新应用每个控件的基础样式
                widget.setStyleSheet(f"""
                    QWidget {{
                        background-color: {t['panel_bg']};
                        color: {t['text_primary']};
                    }}
                    QLabel {{
                        color: {t['text_regular']};
                    }}
                    QSpinBox {{
                        background-color: {t['panel_bg']};
                        color: {t['text_primary']};
                        border: 1px solid {t['border']};
                    }}
                    QRadioButton {{
                        color: {t['text_regular']};
                    }}
                """)
        self.photo_list.viewport().update()
    
    def theme_color(self, key):
        theme = self.THEME["dark" if self.dark_mode else "light"]
        value = theme[key]
        if isinstance(value, QColor):
            return value
        return value

    def apply_stylesheet(self):
        t = self.THEME["dark" if self.dark_mode else "light"]
        
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {t['window_bg']};
                font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
            }}
            QGroupBox {{
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 8px;
                font-weight: bold;
                padding: 8px;
                background-color: {t['panel_bg']};
                color: {t['text_primary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                font-size: 11px;
                color: {t['accent']};
            }}
            QLabel {{
                font-size: 11px;
                color: {t['text_regular']};
            }}
            QComboBox, QLineEdit {{
                border: 1px solid {t['border']};
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 11px;
                min-height: 22px;
                background-color: {t['panel_bg']};
                color: {t['text_primary']};
                selection-background-color: {t['accent']};
                selection-color: {t['panel_bg'] if not self.dark_mode else '#1e1e1e'};
            }}
            QComboBox:hover, QLineEdit:hover {{
                border-color: {t['accent']};
            }}
            QCheckBox {{
                font-size: 11px;
                spacing: 3px;
                color: {t['text_primary']};
            }}
            QFrame {{
                background-color: {t['panel_bg']};
                border-radius: 8px;
            }}
            QStatusBar {{
                background-color: {t['panel_bg']};
                color: {t['text_regular']};
                border-top: 1px solid {t['border']};
            }}
            QSplitter::handle {{
                background-color: {t['border']};
            }}
            QSpinBox {{
                border: 1px solid {t['border']};
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 11px;
                background-color: {t['panel_bg']};
                color: {t['text_primary']};
                selection-background-color: {t['accent']};
            }}
            QSpinBox:hover {{
                border-color: {t['accent']};
            }}
            QProgressBar {{
                border: 1px solid {t['border']};
                border-radius: 4px;
                text-align: center;
                background-color: {t['window_bg']};
                color: {t['text_primary']};
            }}
            QProgressBar::chunk {{
                background-color: {t['accent']};
                border-radius: 3px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t['panel_bg']};
                border: 1px solid {t['border']};
                border-radius: 3px;
                padding: 2px;
                outline: none;
                color: {t['text_primary']};
                selection-background-color: {t['accent']};
                selection-color: white;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 8px;
                min-height: 24px;
                color: {t['text_primary']};
                background-color: {t['panel_bg']};
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {t['hover_bg']};
                color: {t['text_primary']};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {t['accent']};
                color: white;
            }}
            QComboBox::drop-down {{
                border: none;
                background-color: {t['panel_bg']};
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {t['text_secondary']};
                margin-right: 6px;
            }}
        """)
        
        self.photo_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {t['border']};
                border-radius: 4px;
                background-color: {t['panel_bg']};
                padding: 3px;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {t['border_light']};
                padding: 2px;
                background-color: {t['panel_bg']};
            }}
            QListWidget::item:selected {{
                background-color: {t['selected_bg']};
                border: 1px solid {t['accent']};
            }}
            QListWidget::item:hover {{
                background-color: {t['hover_bg']};
            }}
        """)
        
        title_label = self.findChild(QLabel, "panelTitle")
        if title_label:
            title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {t['text_primary']};")
        
        copyright_label = self.findChild(QLabel, "copyrightLabel")
        if copyright_label:
            copyright_label.setStyleSheet(f"font-size: 10px; color: {t['text_secondary']};")
        
        self.photo_count_label.setStyleSheet(f"font-size: 11px; color: {t['text_regular']};")
        self.stats_label.setStyleSheet(f"font-size: 12px; color: {t['text_regular']};")
        self.page_label.setStyleSheet(f"font-size: 12px; color: {t['text_regular']}; margin-left: 20px;")
        
        self.snap_checkbox.setStyleSheet(f"""
            QCheckBox {{ font-size: 11px; color: {t['text_regular']}; margin-left: 10px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; }}
        """)
        
        self.guillotine_check.setStyleSheet(f"""
            QCheckBox {{ font-size: 12px; font-weight: bold; color: {t['text_primary']}; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; }}
        """)
        
        guillotine_hint = self.guillotine_check.parent().findChildren(QLabel)
        for lbl in guillotine_hint:
            if "Guillotine" in lbl.text() or "切纸刀" in lbl.text():
                lbl.setStyleSheet(f"font-size: 9px; color: {t['text_secondary']}; padding-left: 20px;")
                break
        
        canvas_title = self.findChild(QLabel, "canvasTitle")
        if canvas_title:
            canvas_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {t['text_primary']};")
        
        photo_title = self.findChild(QLabel, "photoManagerTitle")
        if photo_title:
            photo_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {t['text_primary']};")
        
        hint_label = self.findChild(QLabel, "photoHint")
        if hint_label:
            hint_label.setStyleSheet(f"font-size: 10px; color: {t['text_secondary']}; padding: 3px;")
        
        disabled_color = t['disabled']
        for btn_name in ["zoomFitBtn", "zoomInBtn", "zoomOutBtn"]:
            btn = self.findChild(QPushButton, btn_name)
            if btn:
                btn.setStyleSheet(f"""
                    QPushButton {{ background-color: {disabled_color}; color: white; border: none;
                                border-radius: 3px; padding: 4px 8px; font-size: 11px; }}
                    QPushButton:hover {{ background-color: {t['text_secondary']}; }}
                """)
        
        zoom_in_btn = self.findChild(QPushButton, "zoomInBtn")
        if zoom_in_btn:
            zoom_in_btn.setStyleSheet(f"""
                QPushButton {{ background-color: {disabled_color}; color: white; border: none;
                            border-radius: 3px; padding: 4px; font-size: 14px; font-weight: bold; }}
                QPushButton:hover {{ background-color: {t['text_secondary']}; }}
            """)
        zoom_out_btn = self.findChild(QPushButton, "zoomOutBtn")
        if zoom_out_btn:
            zoom_out_btn.setStyleSheet(f"""
                QPushButton {{ background-color: {disabled_color}; color: white; border: none;
                            border-radius: 3px; padding: 4px; font-size: 14px; font-weight: bold; }}
                QPushButton:hover {{ background-color: {t['text_secondary']}; }}
            """)
        
        warning_color = self.THEME["dark"]["warning"] if self.dark_mode else "#e6a23c"
        warning_hover = self.THEME["dark"]["warning_hover"] if self.dark_mode else "#ebb563"
        for btn_name in ["prevPageBtn", "nextPageBtn"]:
            btn = self.findChild(QPushButton, btn_name)
            if btn:
                btn.setStyleSheet(f"""
                    QPushButton {{ background-color: {warning_color}; color: white; border: none;
                                border-radius: 3px; padding: 4px 8px; font-size: 11px; }}
                    QPushButton:hover {{ background-color: {warning_hover}; }}
                    QPushButton:disabled {{ background-color: {t['disabled']}; }}
                """)
        
        auto_btn = self.findChild(QPushButton, "autoLayoutBtn")
        if auto_btn:
            success_color = self.THEME["dark"]["success"] if self.dark_mode else "#67c23a"
            success_hover = self.THEME["dark"]["success_hover"] if self.dark_mode else "#85ce61"
            auto_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {success_color};
                    color: white; border: none;
                    border-radius: 4px; padding: 6px 15px;
                    font-size: 12px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {success_hover}; }}
            """)
        
        add_btn = self.findChild(QPushButton, "addPhotoBtn")
        if add_btn:
            add_btn.setStyleSheet(f"""
                QPushButton {{ background-color: {t['accent']}; color: white; border: none;
                            border-radius: 4px; padding: 6px 12px; font-size: 12px; }}
                QPushButton:hover {{ background-color: {t['accent_hover']}; }}
            """)
        clear_btn = self.findChild(QPushButton, "clearPhotosBtn")
        if clear_btn:
            danger_color = self.THEME["dark"]["danger"] if self.dark_mode else "#f56c6c"
            danger_hover = self.THEME["dark"]["danger_hover"] if self.dark_mode else "#f78989"
            clear_btn.setStyleSheet(f"""
                QPushButton {{ background-color: {danger_color}; color: white; border: none;
                            border-radius: 4px; padding: 6px 12px; font-size: 12px; }}
                QPushButton:hover {{ background-color: {danger_hover}; }}
            """)
    
    def select_photos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择照片", "", 
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if files:
            self.add_photos(files)
    
    def add_photos(self, file_paths):
        for file_path in file_paths:
            if any(p.file_path == file_path for p in self.photo_sources):
                continue
            
            # 生成缩略图（修复问题4）
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                continue
            thumbnail = pixmap.scaled(
                50, 50, Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            photo_source = PhotoSource(file_path, thumbnail)
            self.photo_sources.append(photo_source)
            
            item = QListWidgetItem()
            item_widget = PhotoItemWidget(photo_source)
            item_widget.delete_requested.connect(self.on_delete_photo)
            item.setData(Qt.ItemDataRole.UserRole, photo_source.id)
            item.setSizeHint(QSize(220, 75))
            self.photo_list.addItem(item)
            self.photo_list.setItemWidget(item, item_widget)
        
        self.update_stats()
        self.statusBar.showMessage(f"已添加 {len(file_paths)} 张照片")
    
    def on_delete_photo(self, photo_source):
        for i in range(self.photo_list.count()):
            item = self.photo_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == photo_source.id:
                self.photo_list.takeItem(i)
                break
        
        if photo_source in self.photo_sources:
            self.photo_sources.remove(photo_source)
        
        self.update_stats()
        self.statusBar.showMessage(f"已删除照片: {photo_source.file_name}")
    
    def clear_all_photos(self):
        if self.photo_sources:
            reply = QMessageBox.question(
                self, "确认", "确定要清空所有照片吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.photo_sources.clear()
                self.photo_list.clear()
                self.scene.clear()
                self.page_scenes.clear()
                self.current_page = 0
                self.update_stats()
                self.update_page_navigation()
                self.statusBar.showMessage("已清空所有照片")
    
    def update_canvas_size(self, index):
        self.update_preview()
    
    def update_preview(self):
        canvas_data = self.canvas_combo.currentData()
        if not canvas_data:
            return
        
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        self.scene.setSceneRect(0, 0, canvas_w_px, canvas_h_px)
        
        self.scene.clear()
        
        if self.dark_mode:
            scene_bg_color = QColor(45, 45, 45)
            border_color = QColor(80, 90, 110)
            text_color = QColor(120, 120, 120)
        else:
            scene_bg_color = Qt.GlobalColor.white
            border_color = QColor(180, 190, 210)
            text_color = QColor(150, 150, 150)
        
        bg_rect = self.scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                                  QPen(Qt.GlobalColor.transparent),
                                  QBrush(scene_bg_color))
        # 修复问题2：为背景矩形设置数据标记
        bg_rect.setData(0, "background")
        
        border = self.scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                                     QPen(border_color, 3, Qt.PenStyle.DashLine),
                                     QBrush(Qt.GlobalColor.transparent))
        border.setData(0, "background")
        
        try:
            left_margin = float(self.left_margin.text())
            right_margin = float(self.right_margin.text())
            top_margin = float(self.top_margin.text())
            bottom_margin = float(self.bottom_margin.text())
            
            left_margin_px = int(left_margin / 2.54 * dpi)
            right_margin_px = int(right_margin / 2.54 * dpi)
            top_margin_px = int(top_margin / 2.54 * dpi)
            bottom_margin_px = int(bottom_margin / 2.54 * dpi)
            
            if self.dark_mode:
                safe_pen = QColor(255, 100, 100, 120)
                safe_brush = QColor(255, 80, 80, 30)
            else:
                safe_pen = QColor(255, 200, 200, 180)
                safe_brush = QColor(255, 240, 240, 80)
            
            safe_rect = self.scene.addRect(
                left_margin_px, top_margin_px,
                canvas_w_px - left_margin_px - right_margin_px,
                canvas_h_px - top_margin_px - bottom_margin_px,
                QPen(safe_pen, 2),
                QBrush(safe_brush)
            )
            safe_rect.setZValue(-1)
            safe_rect.setData(0, "background")
        except (ValueError, AttributeError):
            pass
        
        if not self.photo_sources:
            text = self.scene.addText("请添加照片并点击自动排版")
            text.setDefaultTextColor(text_color)
            text.setFont(QFont("Microsoft YaHei", 16))
            text.setPos(canvas_w_px/2 - 120, canvas_h_px/2 - 20)
    
    def auto_layout(self):
        if not self.photo_sources:
            QMessageBox.warning(self, "提示", "请先添加照片！")
            return
        
        for i in range(self.photo_list.count()):
            item = self.photo_list.item(i)
            widget = self.photo_list.itemWidget(item)
            if widget:
                widget.get_values()
        
        canvas_data = self.canvas_combo.currentData()
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        try:
            h_space = float(self.h_spacing.text())
            v_space = float(self.v_spacing.text())
        except ValueError:
            h_space = v_space = 0.2
        
        h_spacing_px = int(h_space / 2.54 * dpi)
        v_spacing_px = int(v_space / 2.54 * dpi)
        
        try:
            left_margin = float(self.left_margin.text())
            right_margin = float(self.right_margin.text())
            top_margin = float(self.top_margin.text())
            bottom_margin = float(self.bottom_margin.text())
        except ValueError:
            left_margin = right_margin = top_margin = bottom_margin = 0.3
        
        left_margin_px = int(left_margin / 2.54 * dpi)
        right_margin_px = int(right_margin / 2.54 * dpi)
        top_margin_px = int(top_margin / 2.54 * dpi)
        bottom_margin_px = int(bottom_margin / 2.54 * dpi)
        
        effective_canvas_w = canvas_w_px - left_margin_px - right_margin_px
        effective_canvas_h = canvas_h_px - top_margin_px - bottom_margin_px
        
        if effective_canvas_w <= 0 or effective_canvas_h <= 0:
            QMessageBox.warning(self, "警告", "安全边距设置过大，请减小边距值！")
            return
        
        guillotine_mode = self.guillotine_check.isChecked()
        
        self.layout_worker = LayoutWorker(
            self.photo_sources, effective_canvas_w, effective_canvas_h, h_spacing_px, v_spacing_px, dpi,
            left_margin_px, top_margin_px, guillotine_mode
        )
        self.layout_worker.progress.connect(self.on_layout_progress)
        self.layout_worker.finished.connect(self.on_layout_finished)
        self.layout_worker.start()
        
        self.statusBar.showMessage("正在计算排版...")
    
    def on_layout_progress(self, value):
        self.statusBar.showMessage(f"正在计算排版... {value}%")
    
    def on_layout_finished(self, pages):
        self.page_scenes = []
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        
        canvas_data = self.canvas_combo.currentData()
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        total_photos = 0
        
        try:
            left_margin = float(self.left_margin.text())
            right_margin = float(self.right_margin.text())
            top_margin = float(self.top_margin.text())
            bottom_margin = float(self.bottom_margin.text())
        except ValueError:
            left_margin = right_margin = top_margin = bottom_margin = 0.3
        
        left_margin_px = int(left_margin / 2.54 * dpi)
        top_margin_px = int(top_margin / 2.54 * dpi)
        
        if self.dark_mode:
            scene_bg_color = QColor(45, 45, 45)
            border_color = QColor(80, 90, 110)
            safe_pen_color = QColor(255, 100, 100, 120)
            safe_brush_color = QColor(255, 80, 80, 30)
        else:
            scene_bg_color = Qt.GlobalColor.white
            border_color = QColor(180, 190, 210)
            safe_pen_color = QColor(255, 200, 200, 150)
            safe_brush_color = QColor(255, 240, 240, 50)
        
        for page_data in pages:
            if isinstance(page_data, dict):
                page_items = page_data.get('items', page_data)
                page_cut_lines = page_data.get('cut_lines', [])
            else:
                page_items = page_data
                page_cut_lines = []
            
            page_scene = QGraphicsScene()
            page_scene.setSceneRect(0, 0, canvas_w_px, canvas_h_px)
            
            # 背景矩形，设置data标记（修复问题2）
            bg_rect = page_scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                             QPen(Qt.GlobalColor.transparent),
                             QBrush(scene_bg_color))
            bg_rect.setData(0, "background")
            
            border_rect = page_scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                              QPen(border_color, 3, Qt.PenStyle.DashLine),
                              QBrush(Qt.GlobalColor.transparent))
            border_rect.setData(0, "background")
            
            safe_rect = page_scene.addRect(
                left_margin_px, top_margin_px,
                canvas_w_px - left_margin_px - int(right_margin / 2.54 * dpi),
                canvas_h_px - top_margin_px - int(bottom_margin / 2.54 * dpi),
                QPen(safe_pen_color), QBrush(safe_brush_color)
            )
            safe_rect.setZValue(-1)
            safe_rect.setData(0, "background")
            
            guillotine_mode = self.guillotine_check.isChecked()
            
            for item_data in page_items:
                source_idx = item_data['source_index']
                if source_idx < len(self.photo_sources):
                    photo = self.photo_sources[source_idx]
                    size_info = size_manager.photo_sizes[photo.target_size_index]
                    
                    if item_data.get('rotation', False):
                        w_px = int(size_info["height"] / 2.54 * dpi)
                        h_px = int(size_info["width"] / 2.54 * dpi)
                    else:
                        w_px = int(size_info["width"] / 2.54 * dpi)
                        h_px = int(size_info["height"] / 2.54 * dpi)
                    
                    rotated = item_data.get('rotation', False)
                    photo_item = SnapPhotoItem(photo, w_px, h_px, self.snap_enabled, rotated)
                    photo_item.setPos(item_data['x'], item_data['y'])
                    page_scene.addItem(photo_item)
                    total_photos += 1
            
            self.page_scenes.append(page_scene)
        
        self.current_page = 0
        if self.page_scenes:
            self.scene = self.page_scenes[0]
            self.canvas_view.setScene(self.scene)
            self.zoom_to_fit()
        
        self.update_page_navigation()
        
        page_count = len(self.page_scenes)
        self.statusBar.showMessage(f"排版完成，共 {total_photos} 张照片，{page_count} 页")
        self.stats_label.setText(f"画布: {canvas_w_cm}×{canvas_h_cm}cm | 照片: {total_photos}张 | 页数: {page_count}页 | DPI: {dpi}")
    
    def refresh_page_scenes(self):
        """刷新所有页面场景以应用当前主题 - 修复问题2：通过data标记识别背景矩形"""
        if not self.page_scenes:
            return
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        
        canvas_data = self.canvas_combo.currentData()
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        try:
            left_margin = float(self.left_margin.text())
            right_margin = float(self.right_margin.text())
            top_margin = float(self.top_margin.text())
            bottom_margin = float(self.bottom_margin.text())
        except ValueError:
            left_margin = right_margin = top_margin = bottom_margin = 0.3
        
        left_margin_px = int(left_margin / 2.54 * dpi)
        top_margin_px = int(top_margin / 2.54 * dpi)
        
        if self.dark_mode:
            scene_bg_color = QColor(45, 45, 45)
            border_color = QColor(80, 90, 110)
            safe_pen_color = QColor(255, 100, 100, 120)
            safe_brush_color = QColor(255, 80, 80, 30)
        else:
            scene_bg_color = Qt.GlobalColor.white
            border_color = QColor(180, 190, 210)
            safe_pen_color = QColor(255, 200, 200, 150)
            safe_brush_color = QColor(255, 240, 240, 50)
        
        for page_scene in self.page_scenes:
            # 通过data标记删除背景矩形，而不是脆弱的类型判断
            items_to_remove = []
            for item in page_scene.items():
                if item.data(0) == "background":
                    items_to_remove.append(item)
            
            for item in items_to_remove:
                page_scene.removeItem(item)
            
            # 重新绘制背景
            bg_rect = page_scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                             QPen(Qt.GlobalColor.transparent),
                             QBrush(scene_bg_color))
            bg_rect.setData(0, "background")
            
            border_rect = page_scene.addRect(0, 0, canvas_w_px, canvas_h_px,
                              QPen(border_color, 3, Qt.PenStyle.DashLine),
                              QBrush(Qt.GlobalColor.transparent))
            border_rect.setData(0, "background")
            
            safe_rect = page_scene.addRect(
                left_margin_px, top_margin_px,
                canvas_w_px - left_margin_px - int(right_margin / 2.54 * dpi),
                canvas_h_px - top_margin_px - int(bottom_margin / 2.54 * dpi),
                QPen(safe_pen_color), QBrush(safe_brush_color)
            )
            safe_rect.setZValue(-1)
            safe_rect.setData(0, "background")
    
    def update_page_navigation(self):
        page_count = len(self.page_scenes)
        if page_count > 0:
            self.page_label.setText(f"第 {self.current_page + 1} / {page_count} 页")
            self.prev_page_btn.setEnabled(self.current_page > 0)
            self.next_page_btn.setEnabled(self.current_page < page_count - 1)
        else:
            self.page_label.setText("第 1 页")
            self.prev_page_btn.setEnabled(False)
            self.next_page_btn.setEnabled(False)
    
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.scene = self.page_scenes[self.current_page]
            self.canvas_view.setScene(self.scene)
            self.zoom_to_fit()
            self.update_page_navigation()
    
    def next_page(self):
        if self.current_page < len(self.page_scenes) - 1:
            self.current_page += 1
            self.scene = self.page_scenes[self.current_page]
            self.canvas_view.setScene(self.scene)
            self.zoom_to_fit()
            self.update_page_navigation()
    
    def zoom_to_fit(self):
        self.canvas_view.zoom_to_fit()
    
    def zoom_in(self):
        self.canvas_view.scale(1.2, 1.2)
    
    def zoom_out(self):
        self.canvas_view.scale(1/1.2, 1/1.2)
    
    def on_snap_changed(self, state):
        self.snap_enabled = (state == 2)
        if self.scene:
            for item in self.scene.items():
                if hasattr(item, 'set_snap_enabled'):
                    item.set_snap_enabled(self.snap_enabled)
        self.statusBar.showMessage(f"吸附对齐: {'开启' if self.snap_enabled else '关闭'}")
    
    def update_stats(self):
        count = len(self.photo_sources)
        self.photo_count_label.setText(f"共 {count} 张照片")
    
    def _make_scenes_white_background(self):
        """将页面场景的背景临时设为白色（用于导出），返回保存的原始画笔信息"""
        saved_brushes = []  # [(scene, item, original_brush)]
        for page_scene in self.page_scenes:
            for item in page_scene.items():
                if item.data(0) == "background":
                    # 使用hasattr检查是否有brush/setBrush方法（QAbstractGraphicsShapeItem子类）
                    if hasattr(item, 'brush') and hasattr(item, 'setBrush'):
                        brush = item.brush()
                        # 只处理非透明填充的背景矩形
                        if brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0:
                            # 跳过已经是白色的
                            if brush.color() != Qt.GlobalColor.white:
                                saved_brushes.append((page_scene, item, brush))
                                item.setBrush(QBrush(Qt.GlobalColor.white))
        return saved_brushes
    
    def _restore_scene_backgrounds(self, saved_brushes):
        """恢复场景背景的原始颜色"""
        for scene, item, original_brush in saved_brushes:
            item.setBrush(original_brush)

    def batch_export(self):
        if not self.page_scenes:
            QMessageBox.warning(self, "提示", "没有可导出的排版！请先进行自动排版。")
            return
        
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
        
        output_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not output_dir:
            return
        
        canvas_data = self.canvas_combo.currentData()
        canvas_w_cm = canvas_data["width"]
        canvas_h_cm = canvas_data["height"]
        
        dpi_values = [150, 300, 600, 1200]
        dpi = dpi_values[self.dpi_combo.currentIndex()]
        
        canvas_w_px = int(canvas_w_cm / 2.54 * dpi)
        canvas_h_px = int(canvas_h_cm / 2.54 * dpi)
        
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        base_name = "证件照片排版"
        
        # 导出前将场景背景临时设为白色（修复深色模式导出背景变黑的问题）
        self._saved_background_brushes = self._make_scenes_white_background()
        
        self.export_worker = ExportWorker(
            self.page_scenes, canvas_w_px, canvas_h_px, dpi,
            formats, output_dir, base_name
        )
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.start()
        
        self.statusBar.showMessage("正在导出...")
    
    def on_export_progress(self, value):
        self.progress_bar.setValue(value)
        self.statusBar.showMessage(f"正在导出... {value}%")
    
    def on_export_finished(self, output_dir):
        # 导出完成后恢复场景背景颜色
        if hasattr(self, '_saved_background_brushes'):
            self._restore_scene_backgrounds(self._saved_background_brushes)
            self._saved_background_brushes = []
        
        self.export_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.statusBar.showMessage("导出完成")
        
        QMessageBox.information(
            self, "导出成功",
            f"照片已导出到:\n{output_dir}"
        )
    
    def on_export_error(self, error_msg):
        # 导出失败也要恢复场景背景颜色
        if hasattr(self, '_saved_background_brushes'):
            self._restore_scene_backgrounds(self._saved_background_brushes)
            self._saved_background_brushes = []
        
        self.export_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.statusBar.showMessage("导出失败")
        
        QMessageBox.critical(self, "导出失败", f"导出时发生错误:\n{error_msg}")
    
    # 修复问题3：窗口关闭线程安全处理
    def closeEvent(self, event):
        # 停止并等待布局线程
        if self.layout_worker and self.layout_worker.isRunning():
            self.layout_worker.quit()
            self.layout_worker.wait(1000)
        # 停止并等待导出线程
        if self.export_worker and self.export_worker.isRunning():
            self.export_worker.cancel()  # 设置取消标志
            self.export_worker.quit()
            self.export_worker.wait(1000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    from PySide6.QtWidgets import QStyleFactory
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    
    app.setStyleSheet("""
        QScrollBar:vertical {
            background: #f0f0f0;
            width: 10px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background: #c0c4cc;
            border-radius: 5px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #909399;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background: #f0f0f0;
            height: 10px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal {
            background: #c0c4cc;
            border-radius: 5px;
            min-width: 30px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #909399;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
    """)
    
    window = EnhancedPhotoLayoutTool()
    window.show()
    sys.exit(app.exec())