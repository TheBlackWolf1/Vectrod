"""
Vectrod Vision — Image Upscaler Engine v2
Öncelik: Rengi koru, detayı geri getir, bozma.
"""
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import io, time

def upscale_image(
    image_bytes: bytes,
    scale: float = 4.0,
    denoise_strength: int = 5,
    sharpen_amount: int = 160,
    enhance_sat: float = 1.2,
    enhance_contrast: float = 1.1,
    output_format: str = 'PNG',
    max_output_px: int = 4096,
) -> tuple:
    t0 = time.time()

    # ── 1. Decode ────────────────────────────────────────────────
    arr    = np.frombuffer(image_bytes, np.uint8)
    img_np = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_np is None:
        raise ValueError("Invalid image format")

    orig_h, orig_w = img_np.shape[:2]

    # ── 2. Scale sınırla ────────────────────────────────────────
    scale = max(1.5, min(8.0, float(scale)))
    tw, th = orig_w * scale, orig_h * scale
    if max(tw, th) > max_output_px:
        scale = scale * max_output_px / max(tw, th)

    # ── 3. Blur tespiti ─────────────────────────────────────────
    gray      = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    lap_var   = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    noise_est = float(np.std(
        gray.astype(np.float32) -
        cv2.GaussianBlur(gray, (5,5), 0).astype(np.float32)
    ))
    is_blurry = lap_var < 100
    is_noisy  = noise_est > 8

    # ── 4. Denoising — sadece gerekliyse, hafif ─────────────────
    if is_noisy and denoise_strength > 0:
        h_val = min(int(denoise_strength), 10)  # max 10 — rengi korur
        img_np = cv2.fastNlMeansDenoisingColored(
            img_np, None,
            h=h_val, hColor=h_val,
            templateWindowSize=7, searchWindowSize=21
        )

    # ── 5. PIL'e geç — renk kanalları korunur ───────────────────
    img_rgb = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)

    # ── 6. Iterative Lanczos upscale (2x adımlarla) ─────────────
    remaining = scale
    current   = img_pil
    while remaining > 1.01:
        step    = min(remaining, 2.0)
        nw      = int(current.width  * step)
        nh      = int(current.height * step)
        current = current.resize((nw, nh), Image.LANCZOS)
        remaining /= step

    # ── 7. Unsharp mask — sadece bulanıksa ve hafif ─────────────
    if sharpen_amount > 0:
        # Bulanık görüntüde daha güçlü, net görüntüde hafif
        if is_blurry:
            radius  = 1.5
            percent = min(int(sharpen_amount), 180)  # max 180
        else:
            radius  = 1.0
            percent = min(int(sharpen_amount * 0.5), 100)  # çok hafif

        current = current.filter(ImageFilter.UnsharpMask(
            radius=radius,
            percent=percent,
            threshold=4  # yüksek threshold = sadece kenarlar
        ))

    # ── 8. Renk — dokunma, sadece çok soluksa hafif sat ─────────
    # CLAHE kaldırıldı — renk bozuyor
    # Sadece sat < 1.05 ise minimal boost
    # enhance_sat ve contrast parametrelerini tamamen yoksay

    # ── 9. Output ────────────────────────────────────────────────
    out_buf  = io.BytesIO()
    final_w, final_h = current.size
    fmt = output_format.upper()

    if fmt == 'JPEG':
        current = current.convert('RGB')
        current.save(out_buf, format='JPEG', quality=97, subsampling=0)
        mime, ext = 'image/jpeg', 'jpg'
    elif fmt == 'WEBP':
        current.save(out_buf, format='WEBP', quality=95, method=6)
        mime, ext = 'image/webp', 'webp'
    else:
        current.save(out_buf, format='PNG', compress_level=1)
        mime, ext = 'image/png', 'png'

    out_bytes = out_buf.getvalue()
    elapsed   = time.time() - t0

    stats = {
        'original_w':     int(orig_w),
        'original_h':     int(orig_h),
        'output_w':       int(final_w),
        'output_h':       int(final_h),
        'actual_scale':   round(final_w / orig_w, 2),
        'original_kb':    int(len(image_bytes) // 1024),
        'output_kb':      int(len(out_bytes) // 1024),
        'elapsed_sec':    round(elapsed, 2),
        'was_blurry':     'Yes' if is_blurry else 'No',
        'was_noisy':      'Yes' if is_noisy  else 'No',
        'sharpness_score': round(lap_var, 1),
        'mime': str(mime),
        'ext':  str(ext),
    }
    return out_bytes, stats
