#!/usr/bin/env python3
"""量出每张气泡的点九数据（capInsets / contentInsets）。

为什么要量：这些气泡的装饰（猫、翅膀、云朵）从四边伸进来多少各不相同。
拿「高 × 某个系数」去猜，套在 21 张图上必然出事 —— 字会压在装饰上，
或者飘到框外，拉伸时装饰还会变形。

怎么量，三步：

1. 内壁矩形 —— 从图片正中往外扫，颜色一变就是描边/装饰的起点。
   取一条 41 列（或 17 行）的中位色带来扫，装饰性的小圆点骗不停它。
2. 收边 —— 上一步会有几张穿到装饰上（比如泡子和装饰同为白色时）。
   所以再逐边往里退，直到整条边都落在干净填充里。
   这个矩形就是 contentInsets：文字落在这里，既不压装饰也不贴边。
3. 缝 —— 只留一条窄缝给拉伸，其余全划进保护区（capInsets）。
   · 横缝取内壁中间 40%：上下两条边在那儿只是描边，横着拉看不出来。
   · 竖缝只有 8px，而且**不放正中间** —— 纵向拉伸等于把缝那几行原地复制，
     左右两列站着猫和翅膀，落在眼睛或耳朵上就会扯出竖条纹。
     所以逐行算了一遍两侧的上下起伏，挑最平的一行当缝。

用法：
    python3 tools/measure.py Assets/png            # 打印结果
    python3 tools/measure.py Assets/png --json bubbles.json
    python3 tools/measure.py Assets/png --swift    # 直接吐 Swift 数组

需要 pillow / numpy / scipy。
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage

SCALE = 3          # 素材是 @3x，pt = px / 3
SEAM_PX = 8        # 竖缝宽度
SEAM_FRAC_X = 0.40 # 横缝占内壁宽的比例


def load(path):
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    return a[..., :3], a[..., 3]


def _row_bg(rgb, mask):
    """每一行的中位色 = 那一行「本该是什么颜色」"""
    bg = rgb.copy()
    for y in range(rgb.shape[0]):
        sel = mask[y]
        if sel.sum() >= 15:
            bg[y] = np.median(rgb[y][sel], axis=0)
    return bg


def _core(rgb, al, tol=9, iters=3):
    """填充区：颜色贴着行中位色的那一大块，迭代几次收敛"""
    solid = al > 250
    mask = solid.copy()
    core = None
    for _ in range(iters):
        bg = _row_bg(rgb, mask)
        cand = (np.abs(rgb - bg).max(2) < tol) & solid
        cand = ndimage.binary_opening(cand, np.ones((3, 3)))
        lab, n = ndimage.label(cand)
        if n == 0:
            return None, None
        core = lab == (np.bincount(lab.ravel())[1:].argmax() + 1)
        mask = core
    return core, _row_bg(rgb, core)


def _scan_edge(prof, alpha, start, step, thr, run=4):
    """从中心往外走，连着 run 个像素变色就算撞到边了"""
    base = prof[start]
    bad, last, i = 0, start, start
    while True:
        i += step
        if i < 0 or i >= len(prof):
            return last
        if alpha[i] < 250 or np.abs(prof[i] - base).max() > thr:
            bad += 1
            if bad >= run:
                return last - step * (run - 1)
        else:
            bad, last = 0, i


def inner_rect(rgb, al, thr=16, guard=3):
    """内壁矩形：先扫一圈，再逐边往里退到干净为止"""
    h, w = al.shape
    cy, cx = h // 2, w // 2
    cols = slice(max(0, cx - 20), min(w, cx + 21))
    rows = slice(max(0, cy - 8), min(h, cy + 9))
    vprof, valp = np.median(rgb[:, cols], axis=1), np.median(al[:, cols], axis=1)
    hprof, halp = np.median(rgb[rows, :], axis=0), np.median(al[rows, :], axis=0)
    y0 = _scan_edge(vprof, valp, cy, -1, thr)
    y1 = _scan_edge(vprof, valp, cy, +1, thr)
    x0 = _scan_edge(hprof, halp, cx, -1, thr)
    x1 = _scan_edge(hprof, halp, cx, +1, thr)

    # 收边：泡子和装饰同色时上面会穿过去，往里退到整条边都干净
    core, bg = _core(rgb, al)
    if core is None:
        return [int(x0), int(y0), int(x1), int(y1)]
    filled = ndimage.binary_fill_holes(core)
    holes = filled & ~core
    lab, n = ndimage.label(holes, np.ones((3, 3)))
    # 图案自带的小圆点是设计，不算「撞到装饰」
    deco = np.zeros_like(holes)
    round_ = []
    for i in range(1, n + 1):
        ys, xs = np.where(lab == i)
        if len(ys) < 4:
            continue
        bw, bh = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        if 5 <= bw <= 11 and 5 <= bh <= 11 and abs(bw - bh) <= 3 and len(ys) / (bw * bh) >= .55:
            round_.append((i, float((rgb[ys, xs].mean(1) - bg[ys, xs].mean(1)).mean())))
    if len(round_) >= 5:
        med = np.median([s for _, s in round_])
        keep = [i for i, s in round_ if abs(s - med) <= 18]
        if keep:
            deco = np.isin(lab, keep)

    med21 = np.dstack([ndimage.median_filter(rgb[..., c], size=21) for c in range(3)])
    dirty = ((np.abs(rgb - med21).max(2) > 20) | (al < 250)) \
        & ~ndimage.binary_dilation(deco, np.ones((7, 7)))
    mx, my = (x0 + x1) // 2, (y0 + y1) // 2
    while x0 < mx - 20 and dirty[y0:y1, x0].any(): x0 += 1
    while x1 > mx + 20 and dirty[y0:y1, x1].any(): x1 -= 1
    while y0 < my - 8 and dirty[y0, x0:x1].any(): y0 += 1
    while y1 > my + 8 and dirty[y1, x0:x1].any(): y1 -= 1
    return [int(x0 + guard), int(y0 + guard), int(x1 - guard), int(y1 - guard)]


def seams(rgb, al, rect):
    """挑缝：横缝取中间 40%，竖缝挑左右两侧最平坦的一行"""
    h, w = al.shape
    x0, y0, x1, y1 = rect
    iw = x1 - x0
    sx0 = x0 + iw * (1 - SEAM_FRAC_X) / 2
    sx1 = x1 - iw * (1 - SEAM_FRAC_X) / 2

    side = np.zeros(w, bool)
    side[:int(sx0)] = True
    side[int(sx1):] = True
    a = np.dstack([rgb, al])
    updown = np.abs(a[1:] - a[:-1]).max(2)          # 每行跟下一行差多少
    score = updown[:, side].mean(1)
    lo, hi = y0 + 2, min(y1 - SEAM_PX - 2, h - SEAM_PX - 2)
    if hi <= lo:
        sy0 = (y0 + y1) // 2
    else:
        win = np.array([score[y:y + SEAM_PX].mean() for y in range(lo, hi)])
        sy0 = lo + int(win.argmin())
    return sx0, sy0, sx1, sy0 + SEAM_PX


def measure(path):
    rgb, al = load(path)
    h, w = al.shape
    rect = inner_rect(rgb, al)
    sx0, sy0, sx1, sy1 = seams(rgb, al, rect)
    x0, y0, x1, y1 = rect
    return dict(
        pixelSize=[w, h], scale=SCALE, innerRect=rect,
        capInsets=dict(top=round(sy0 / SCALE, 1), leading=round(sx0 / SCALE, 1),
                       bottom=round((h - 1 - sy1) / SCALE, 1),
                       trailing=round((w - 1 - sx1) / SCALE, 1)),
        # 文字左右各留 2pt 呼吸，上下就贴着内壁走
        contentInsets=dict(top=round(y0 / SCALE, 1), leading=round(x0 / SCALE + 2, 1),
                           bottom=round((h - 1 - y1) / SCALE, 1),
                           trailing=round((w - 1 - x1) / SCALE + 2, 1)),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="放 png 的目录")
    ap.add_argument("--json", help="写到这个文件")
    ap.add_argument("--swift", action="store_true", help="吐 Swift 数组")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.dir) if f.endswith(".png"))
    if not files:
        sys.exit(f"{args.dir} 里没有 png")
    out = []
    for f in files:
        sid = f[:-4]
        m = measure(os.path.join(args.dir, f))
        m.update(id=sid, name=sid, file=f)
        out.append(m)
        if not args.swift:
            c, p = m["capInsets"], m["contentInsets"]
            print(f"{sid:13s} {m['pixelSize'][0]}x{m['pixelSize'][1]}  "
                  f"cap 上{c['top']:5.1f} 左{c['leading']:5.1f} 下{c['bottom']:5.1f} 右{c['trailing']:5.1f}  "
                  f"pad 上{p['top']:5.1f} 左{p['leading']:5.1f} 下{p['bottom']:5.1f} 右{p['trailing']:5.1f}")

    if args.swift:
        for m in out:
            c, p = m["capInsets"], m["contentInsets"]
            print(f'''        .init(id: "{m['id']}", name: "{m['name']}", asset: "BubbleSkin-{m['id']}",
              cap: .init(top: {c['top']}, leading: {c['leading']}, bottom: {c['bottom']}, trailing: {c['trailing']}),
              pad: .init(top: {p['top']}, leading: {p['leading']}, bottom: {p['bottom']}, trailing: {p['trailing']})),''')
    if args.json:
        for m in out:
            m.pop("innerRect", None)
        json.dump({"version": 1, "bubbles": out}, open(args.json, "w"),
                  ensure_ascii=False, indent=2)
        print(f"\n写好 {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
