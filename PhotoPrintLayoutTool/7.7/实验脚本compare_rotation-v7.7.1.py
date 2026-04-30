"""
对比三种子条带旋转策略的压力测试。
使用大批量照片给子条带施加压力，暴露差异。
"""
import random, time

PHOTO_SIZES = [
    ("1寸", 2.5, 3.5),
    ("小1寸", 2.2, 3.2),
    ("大1寸", 3.3, 4.8),
    ("2寸", 3.5, 4.9),
    ("5寸横", 12.7, 8.9),
    ("6寸横", 15.2, 10.2),
    ("明信片横", 14.8, 10.0),
    ("方形", 10.0, 10.0),
]

CANVASES = [
    ("A4竖放", 21.0, 29.7),
    ("A4横放", 29.7, 21.0),
    ("6寸竖放", 10.2, 15.2),
    ("6寸横放", 15.2, 10.2),
]

DPI = 300
H_SPACING_CM = 0.2
V_SPACING_CM = 0.2
MARGIN_CM = 0.3


def cm_to_px(cm):
    return int(cm / 2.54 * DPI)


class Rect:
    def __init__(self, src_idx, w_cm, h_cm):
        self.src_idx = src_idx
        self.w = cm_to_px(w_cm)
        self.h = cm_to_px(h_cm)
        self.slot_w = self.w + cm_to_px(H_SPACING_CM)
        self.slot_h = self.h + cm_to_px(V_SPACING_CM)
        self.w_cm = w_cm
        self.h_cm = h_cm


def double_strip_packing(rects, canvas_w_px, canvas_h_px, strategy="B"):
    remaining = [r for r in rects]
    remaining.sort(key=lambda r: (-r.slot_h, -r.slot_w))
    pages = []
    current_page = []
    current_y = cm_to_px(MARGIN_CM)

    def can_fit_row(h):
        return current_y + h <= canvas_h_px

    def flush():
        nonlocal current_page, current_y
        if current_page:
            pages.append(list(current_page))
            current_page = []
            current_y = cm_to_px(MARGIN_CM)

    while remaining:
        max_height = max(r.slot_h for r in remaining)
        same_height = [r for r in remaining if r.slot_h == max_height]
        same_height.sort(key=lambda r: -r.slot_w)

        if not can_fit_row(max_height):
            flush()
            if not can_fit_row(max_height):
                break

        row_y = current_y
        used_width = cm_to_px(MARGIN_CM)
        placed_idx = []

        for idx, r in enumerate(same_height):
            if used_width + r.slot_w <= canvas_w_px:
                current_page.append({
                    'x': used_width, 'y': row_y,
                    'w': r.w, 'h': r.h, 'src': r.src_idx, 'rot': False
                })
                used_width += r.slot_w
                placed_idx.append(idx)
            else:
                break

        for idx in sorted(placed_idx, reverse=True):
            same_height.pop(idx)

        other = [r for r in remaining if r.slot_h != max_height]
        remaining = same_height + other
        remaining.sort(key=lambda r: (-r.slot_h, -r.slot_w))

        remaining_width = canvas_w_px - used_width
        if remaining_width > 0:
            sub_strip_y = row_y
            while True:
                cand = None
                for r in remaining:
                    if r.slot_w <= remaining_width:
                        cand = r
                        break
                if cand is None:
                    break

                rotated = decide_rotation(cand, remaining, remaining_width, strategy)
                sub_strip_width = cand.slot_h if rotated else cand.slot_w
                sub_y = sub_strip_y
                placed = []

                if rotated:
                    cw, ch = cand.h, cand.w
                    c_slot_h = cand.slot_w
                else:
                    cw, ch = cand.w, cand.h
                    c_slot_h = cand.slot_h

                yp = sub_y
                if yp + ch <= canvas_h_px and yp + c_slot_h <= row_y + max_height:
                    current_page.append({
                        'x': used_width, 'y': yp,
                        'w': cw, 'h': ch, 'src': cand.src_idx, 'rot': rotated
                    })
                    placed.append(cand)
                    sub_y = yp + c_slot_h

                while sub_y < row_y + max_height:
                    best = None
                    best_rot = False
                    for r in remaining:
                        if r in placed:
                            continue
                        if r.slot_w <= sub_strip_width:
                            if strategy == "B" and rotated and r.slot_w < r.slot_h and r.slot_h <= sub_strip_width:
                                best = r; best_rot = True; break
                            best = r; best_rot = False; break
                        elif r.slot_w > r.slot_h and r.slot_h <= sub_strip_width:
                            best = r; best_rot = True; break
                    if best is None:
                        break
                    iw, ih = (best.h, best.w) if best_rot else (best.w, best.h)
                    i_slot_h = best.slot_w if best_rot else best.slot_h
                    yp = sub_y
                    if yp + ih <= canvas_h_px and yp + i_slot_h <= row_y + max_height:
                        current_page.append({
                            'x': used_width, 'y': yp,
                            'w': iw, 'h': ih, 'src': best.src_idx, 'rot': best_rot
                        })
                        placed.append(best)
                        sub_y = yp + i_slot_h
                    else:
                        break

                for r in placed:
                    remaining.remove(r)
                remaining_width -= sub_strip_width
                used_width += sub_strip_width
                if remaining_width <= 0:
                    break

        current_y += max_height + cm_to_px(V_SPACING_CM)

    if current_page:
        pages.append(list(current_page))
    return pages


def decide_rotation(cand, remaining, remaining_width, strategy):
    if strategy == "A":
        if cand.slot_w > cand.slot_h:
            return cand.slot_h <= remaining_width
        if cand.slot_w < cand.slot_h:
            remaining_after = remaining_width - cand.slot_w
            can_fit = any(r2.slot_w <= remaining_after for r2 in remaining if r2 is not cand)
            if not can_fit and cand.slot_h <= remaining_width:
                return True
        return False
    elif strategy == "C":
        if cand.slot_w < cand.slot_h:
            return cand.slot_h <= remaining_width
        if cand.slot_w > cand.slot_h:
            remaining_after = remaining_width - cand.slot_h
            can_fit = any(r2.slot_w <= remaining_after for r2 in remaining if r2 is not cand)
            if can_fit and cand.slot_h <= remaining_width:
                return True
        return False
    else:
        rotated = False
        if cand.slot_w < cand.slot_h:
            remaining_after = remaining_width - cand.slot_w
            can_fit = any(r2.slot_w <= remaining_after for r2 in remaining if r2 is not cand)
            if not can_fit and cand.slot_h <= remaining_width:
                rotated = True
        elif cand.slot_w > cand.slot_h:
            remaining_after = remaining_width - cand.slot_h
            can_fit = any(r2.slot_w <= remaining_after for r2 in remaining if r2 is not cand)
            if can_fit and cand.slot_h <= remaining_width:
                rotated = True
        return rotated


def calc_metrics(pages, canvas_w_px, canvas_h_px):
    if not pages:
        return 0, 0, 0.0
    total_area = sum(item['w'] * item['h'] for page in pages for item in page)
    total_photos = sum(len(p) for p in pages)
    page_area = len(pages) * canvas_w_px * canvas_h_px
    return len(pages), total_photos, total_area / page_area * 100


def count_rotated(pages):
    return sum(1 for page in pages for item in page if item['rot'])


def make_test(name, spec):
    name_map = {s[0]: (s[1], s[2]) for s in PHOTO_SIZES}
    rects = []
    idx = 0
    for sz_name, cnt in spec:
        if sz_name in name_map:
            w, h = name_map[sz_name]
            for _ in range(cnt):
                rects.append(Rect(idx, w, h))
            idx += 1
    return name, rects


def run():
    # ===== 压力测试用例 =====
    tests = [
        make_test("50张1寸+10张横",
            [("1寸", 50), ("5寸横", 5), ("6寸横", 5)]),
        make_test("30张2寸+20张明信片横",
            [("2寸", 30), ("明信片横", 20)]),
        make_test("40张1寸+40张2寸",
            [("1寸", 40), ("2寸", 40)]),
        make_test("20张横+20张方+20张1寸",
            [("5寸横", 10), ("6寸横", 10), ("方形", 10), ("1寸", 20)]),
        make_test("100张1寸",
            [("1寸", 100)]),
        make_test("50张5寸横+50张1寸",
            [("5寸横", 50), ("1寸", 50)]),
        make_test("200张1寸",
            [("1寸", 200)]),
    ]

    for cn, cw_cm, ch_cm in CANVASES:
        cw = cm_to_px(cw_cm)
        ch = cm_to_px(ch_cm)
        print(f"\n{'='*90}")
        print(f"  画布: {cn} ({cw_cm:.1f}x{ch_cm:.1f}cm = {cw}x{ch}px)")
        print(f"{'='*90}")
        print(f"{'测试集':<30} {'A(先竖)':>20} {'B(当前)':>20} {'C(先横)':>20}")
        print(f"{'':<30} {'页数/利用率/旋转':>20} {'页数/利用率/旋转':>20} {'页数/利用率/旋转':>20}")
        print("-" * 90)

        for tname, rects in tests:
            results = {}
            for s in ["A", "B", "C"]:
                pages = double_strip_packing(rects, cw, ch, s)
                n, t, u = calc_metrics(pages, cw, ch)
                r = count_rotated(pages)
                results[s] = (n, u, r)

            marks = ["", "", ""]
            best_n = min(results[s][0] for s in ["A", "B", "C"])
            best_u = max(results[s][1] for s in ["A", "B", "C"] if results[s][0] == best_n)
            for i, s in enumerate(["A", "B", "C"]):
                n, u, r = results[s]
                if n == best_n and abs(u - best_u) < 0.5:
                    marks[i] = " [BEST]"

            for i, s in enumerate(["A", "B", "C"]):
                n, u, r = results[s]
                print(f"{tname:<30} {n:>3d}p {u:>5.1f}% {r:>3d}r{marks[i]:>8}", end="")
                if i < 2:
                    print(f"{' |':>4}", end="")
            print()


if __name__ == "__main__":
    run()
