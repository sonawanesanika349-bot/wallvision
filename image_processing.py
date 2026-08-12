import cv2
import numpy as np

COLOR_MAP = {
    "white": (255, 255, 255),
    "black": (25, 25, 25),
    "red": (220, 70, 70),
    "green": (75, 160, 100),
    "blue": (80, 130, 220),
    "yellow": (235, 205, 70),
    "orange": (235, 145, 70),
    "pink": (225, 125, 165),
    "purple": (145, 100, 190),
    "brown": (145, 95, 60),
    "gray": (145, 145, 145),
    "beige": (220, 205, 175),
}

def hex_to_bgr(hex_color):
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError("Invalid color")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return np.array([b, g, r], dtype=np.uint8)

def nearest_color_name(rgb):
    target = np.array(rgb, dtype=np.float32)
    best_name, best_dist = "gray", float("inf")
    for name, bgr in COLOR_MAP.items():
        candidate = np.array([bgr[2], bgr[1], bgr[0]], dtype=np.float32)
        dist = np.linalg.norm(target - candidate)
        if dist < best_dist:
            best_name, best_dist = name, dist
    return best_name

def dominant_room_color(image):
    small = cv2.resize(image, (100, 100))
    pixels = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).reshape(-1, 3)
    # Ignore extremely dark/light outliers.
    brightness = pixels.mean(axis=1)
    pixels = pixels[(brightness > 35) & (brightness < 245)]
    if len(pixels) == 0:
        pixels = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).reshape(-1, 3)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.8)
    pixels32 = np.float32(pixels)
    _, _, centers = cv2.kmeans(pixels32, 4, None, criteria, 4, cv2.KMEANS_PP_CENTERS)
    centers = np.uint8(centers)
    avg = centers.mean(axis=0)
    return nearest_color_name(avg.astype(np.uint8))

def detect_wall_mask(image):
    """
    Heuristic wall detector for a no-API prototype.

    The method favors:
      - large low-texture regions
      - colors common in the upper/middle portion
      - pixels near the dominant wall-like color
      - connected regions that occupy a meaningful portion of the image

    It is not a trained semantic segmentation model.
    """
    h, w = image.shape[:2]
    scale = min(1.0, 900.0 / max(h, w))
    if scale < 1:
        work = cv2.resize(image, None, fx=scale, fy=scale)
    else:
        work = image.copy()

    H, W = work.shape[:2]
    lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)

    # Estimate wall color from a broad central/upper region.
    y1, y2 = int(H * 0.10), int(H * 0.75)
    x1, x2 = int(W * 0.10), int(W * 0.90)
    roi = lab[y1:y2, x1:x2]
    pixels = roi.reshape(-1, 3).astype(np.float32)

    # K-means finds broad surfaces better than a single average.
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 1.0)
    k = min(4, max(2, len(pixels) // 5000))
    _, labels, centers = cv2.kmeans(
        pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )

    counts = np.bincount(labels.flatten())
    # Prefer a large cluster with moderate saturation.
    centers = centers.astype(np.float32)
    best = int(np.argmax(counts))
    target_lab = centers[best]

    dist = np.linalg.norm(lab.astype(np.float32) - target_lab, axis=2)
    mask = np.uint8(dist < 34) * 255

    # Walls are usually less saturated than furniture/decor.
    sat = hsv[:, :, 1]
    low_sat = np.uint8(sat < 115) * 255
    mask = cv2.bitwise_and(mask, low_sat)

    # Remove very dark floor-like regions.
    value = hsv[:, :, 2]
    bright_enough = np.uint8(value > 65) * 255
    mask = cv2.bitwise_and(mask, bright_enough)

    # Favor central/upper image and remove a bottom strip.
    region = np.zeros_like(mask)
    region[int(H*0.05):int(H*0.88), int(W*0.04):int(W*0.96)] = 255
    mask = cv2.bitwise_and(mask, region)

    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)

    # Keep large connected components.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    clean = np.zeros_like(mask)
    min_area = max(1500, int(H * W * 0.015))
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_area:
            clean[labels == i] = 255

    # If the heuristic is too strict, use a broad central mask as fallback.
    ratio = np.count_nonzero(clean) / float(H * W)
    if ratio < 0.08:
        fallback = np.zeros_like(mask)
        fallback[int(H*0.08):int(H*0.80), int(W*0.06):int(W*0.94)] = 255
        clean = cv2.bitwise_and(mask, fallback)

    # Resize to original image dimensions.
    if scale < 1:
        clean = cv2.resize(clean, (w, h), interpolation=cv2.INTER_NEAREST)

    # Final edge-aware smoothing.
    clean = cv2.GaussianBlur(clean, (9, 9), 0)
    return clean

def apply_wall_color(image, mask, hex_color, strength=0.78):
    paint_bgr = hex_to_bgr(hex_color)

    # Preserve luminance while changing chroma.
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    paint_hsv = cv2.cvtColor(
        np.uint8([[paint_bgr]]), cv2.COLOR_BGR2HSV
    )[0, 0].astype(np.float32)

    mask_f = (mask.astype(np.float32) / 255.0) * strength

    hsv[:, :, 0] = hsv[:, :, 0] * (1 - mask_f) + paint_hsv[0] * mask_f
    hsv[:, :, 1] = hsv[:, :, 1] * (1 - mask_f) + max(70, paint_hsv[1]) * mask_f

    colored = cv2.cvtColor(np.uint8(np.clip(hsv, 0, 255)), cv2.COLOR_HSV2BGR)

    # Small blend with original keeps texture and shadows.
    alpha = (mask.astype(np.float32) / 255.0)[:, :, None] * 0.70
    result = (
        colored.astype(np.float32) * alpha
        + image.astype(np.float32) * (1 - alpha)
    )
    return np.uint8(np.clip(result, 0, 255))

def process_image(image, hex_color):
    mask = detect_wall_mask(image)
    result = apply_wall_color(image, mask, hex_color)

    detected = dominant_room_color(image)
    wall_percentage = round(float(np.count_nonzero(mask)) / mask.size * 100, 1)

    return result, detected, wall_percentage
