"""
Numpy-based layer compositing engine.
All pixel arrays are float32, shape (N, 4) = (H*W, RGBA), linear colour space.
"""

import numpy as np
import bpy


# ── Colour-space helpers ──────────────────────────────────────────────────────

def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """(N,3) float32 -> (N,3) HSV."""
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc
    v = maxc

    with np.errstate(divide='ignore', invalid='ignore'):
        s  = np.where(maxc > 1e-10, delta / maxc, 0.0)
        rc = np.where(delta > 1e-10, (maxc - r) / delta, 0.0)
        gc = np.where(delta > 1e-10, (maxc - g) / delta, 0.0)
        bc = np.where(delta > 1e-10, (maxc - b) / delta, 0.0)

    h = np.where(r == maxc, bc - gc,
        np.where(g == maxc, 2.0 + rc - bc,
                             4.0 + gc - rc))
    h = np.where(delta < 1e-10, 0.0, (h / 6.0) % 1.0)

    return np.stack([h, s, v], axis=1)


def _hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
    """(N,3) HSV -> (N,3) float32."""
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    h6 = h * 6.0
    i  = np.floor(h6).astype(np.int32) % 6
    f  = h6 - np.floor(h6)
    p  = v * (1.0 - s)
    q  = v * (1.0 - f * s)
    t  = v * (1.0 - (1.0 - f) * s)

    r = np.select([i==0, i==1, i==2, i==3, i==4, i==5], [v, q, p, p, t, v])
    g = np.select([i==0, i==1, i==2, i==3, i==4, i==5], [t, v, v, q, p, p])
    b = np.select([i==0, i==1, i==2, i==3, i==4, i==5], [p, p, t, v, v, q])

    return np.stack([r, g, b], axis=1)


# ── Adjustments ───────────────────────────────────────────────────────────────

def apply_adjustments(layer, pix: np.ndarray) -> np.ndarray:
    """Apply the layer's adjustment FX in-place on a copy. pix: (N,4)."""
    adj = layer.adjustment_type
    if adj == 'NONE':
        return pix

    out = pix.copy()

    if adj == 'BRIGHTNESS_CONTRAST':
        # OpenCV-style: scale contrast around 0.5 then shift brightness
        s  = layer.contrast + 1.0
        sh = -0.5 * layer.contrast + layer.brightness
        out[:, :3] = np.clip(s * out[:, :3] + sh, 0.0, 1.0)

    elif adj == 'HSV':
        hsv = _rgb_to_hsv(out[:, :3])
        hsv[:, 0] = (hsv[:, 0] + layer.hue - 0.5) % 1.0
        hsv[:, 1] = np.clip(hsv[:, 1] * layer.saturation, 0.0, 1.0)
        hsv[:, 2] = np.clip(hsv[:, 2] * layer.value_mult,  0.0, 1.0)
        out[:, :3] = np.clip(_hsv_to_rgb(hsv), 0.0, 1.0)

    elif adj == 'LEVELS':
        lo   = layer.levels_in_min
        hi   = max(layer.levels_in_max, lo + 1e-6)
        gam  = max(layer.levels_gamma,  1e-6)
        olo  = layer.levels_out_min
        ohi  = layer.levels_out_max
        rgb  = np.clip((out[:, :3] - lo) / (hi - lo), 0.0, 1.0)
        rgb  = np.power(rgb, 1.0 / gam)
        out[:, :3] = np.clip(olo + rgb * (ohi - olo), 0.0, 1.0)

    return out


# ── Pixel source ──────────────────────────────────────────────────────────────

def get_layer_pixels(layer, width: int, height: int):
    """Return (H*W, 4) float32 array for the layer, or None if unavailable."""
    n = width * height

    if layer.type == 'FILL':
        pix = np.empty((n, 4), dtype=np.float32)
        c = layer.fill_color
        pix[:, 0] = c[0]; pix[:, 1] = c[1]
        pix[:, 2] = c[2]; pix[:, 3] = c[3]
        return pix

    img = layer.image
    if img is None:
        return None
    if img.size[0] != width or img.size[1] != height:
        return None

    return np.array(img.pixels[:], dtype=np.float32).reshape(n, 4)


# ── Blend modes ───────────────────────────────────────────────────────────────

def _blend(base: np.ndarray, overlay: np.ndarray,
           alpha: np.ndarray, mode: str) -> np.ndarray:
    """
    Combine overlay onto base using the given blend mode.
    base, overlay: (N,3); alpha: (N,1). Returns new (N,3) result.
    """
    def lerp(a, b, t): return a * (1.0 - t) + b * t

    if   mode == 'NORMAL':     blended = overlay
    elif mode == 'MULTIPLY':   blended = base * overlay
    elif mode == 'SCREEN':     blended = 1.0 - (1.0 - base) * (1.0 - overlay)
    elif mode == 'ADD':        blended = np.clip(base + overlay, 0.0, 1.0)
    elif mode == 'SUBTRACT':   blended = np.clip(base - overlay, 0.0, 1.0)
    elif mode == 'DARKEN':     blended = np.minimum(base, overlay)
    elif mode == 'LIGHTEN':    blended = np.maximum(base, overlay)
    elif mode == 'DIFFERENCE': blended = np.abs(base - overlay)

    elif mode == 'OVERLAY':
        mask = base < 0.5
        blended = np.where(mask,
            2.0 * base * overlay,
            1.0 - 2.0 * (1.0 - base) * (1.0 - overlay))

    elif mode == 'SOFT_LIGHT':
        mask = overlay < 0.5
        blended = np.where(mask,
            base - (1.0 - 2.0 * overlay) * base * (1.0 - base),
            base + (2.0 * overlay - 1.0) * (np.sqrt(np.clip(base, 0, 1)) - base))

    elif mode == 'HARD_LIGHT':
        mask = overlay < 0.5
        blended = np.where(mask,
            2.0 * base * overlay,
            1.0 - 2.0 * (1.0 - base) * (1.0 - overlay))

    elif mode in ('HUE', 'SATURATION', 'COLOR', 'VALUE'):
        base_hsv = _rgb_to_hsv(base)
        over_hsv = _rgb_to_hsv(overlay)
        result   = base_hsv.copy()
        if mode == 'HUE':
            result[:, 0] = over_hsv[:, 0]
        elif mode == 'SATURATION':
            result[:, 1] = over_hsv[:, 1]
        elif mode == 'COLOR':
            result[:, 0] = over_hsv[:, 0]
            result[:, 1] = over_hsv[:, 1]
        elif mode == 'VALUE':
            result[:, 2] = over_hsv[:, 2]
        blended = np.clip(_hsv_to_rgb(result), 0.0, 1.0)

    else:
        blended = overlay

    return lerp(base, blended, alpha)


# ── Main compositor ───────────────────────────────────────────────────────────

def composite_stack(obj) -> bool:
    """
    Flatten the object's layer stack into its composite image.
    Returns True on success.
    """
    stack     = obj.texture_layer_stack
    comp_img  = stack.composite_image
    if comp_img is None:
        return False

    w, h = comp_img.size[0], comp_img.size[1]
    n    = w * h

    # Start with transparent black
    res_rgb = np.zeros((n, 3), dtype=np.float32)
    res_a   = np.zeros((n, 1), dtype=np.float32)

    # Iterate bottom → top (reversed list = bottom layer first)
    for layer in reversed(list(stack.layers)):
        if not layer.visible:
            continue

        pix = get_layer_pixels(layer, w, h)
        if pix is None:
            continue

        pix = apply_adjustments(layer, pix)

        lay_rgb = pix[:, :3]
        lay_a   = pix[:, 3:4] * layer.opacity

        res_rgb = _blend(res_rgb, lay_rgb, lay_a, layer.blend_mode)
        res_a   = res_a + lay_a * (1.0 - res_a)

    flat = np.concatenate([res_rgb, res_a], axis=1).flatten()
    comp_img.pixels[:] = flat.tolist()
    comp_img.update()

    # Signal all editors to redraw
    screen = getattr(bpy.context, 'screen', None)
    if screen:
        for area in screen.areas:
            area.tag_redraw()

    return True
