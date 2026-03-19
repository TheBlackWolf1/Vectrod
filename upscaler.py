"""
Vectrod Vision — Image Upscaler Engine
OpenCV + Pillow tabanlı gerçek 4K upscaler
"""
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import io, math, time

def analyze_image(img_np):
    """Görüntüyü analiz et — blur, noise, renk dağılımı."""
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    # Laplacian variance = sharpness score
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Noise estimate
    h, w = gray.shape
    noise = np.std(gray.astype(float) - cv2.GaussianBlur(gray, (5,5), 0).astype(float))
    return {
        'sharpness': float(lap_var),
        'noise': float(noise),
        'width': w,
        'height': h,
        'is_blurry': lap_var < 100,
        'is_noisy': noise > 8,
    }

def denoise(img_np, strength=7):
    """Gürültü gider — Non-local Means Denoising."""
    return cv2.fastNlMeansDenoisingColored(
        img_np, None,
        h=strength, hColor=strength,
        templateWindowSize=7, searchWindowSize=21
    )

def upscale_lanczos(img_pil, scale):
    """Lanczos resampling — en kaliteli interpolasyon."""
    w, h = img_pil.size
    new_w = int(w * scale)
    new_h = int(h * scale)
    # Lanczos = ANTIALIAS = en kaliteli
    return img_pil.resize((new_w, new_h), Image.LANCZOS)

def sharpen_unsharp_mask(img_pil, radius=2.0, percent=180, threshold=3):
    """Unsharp Mask — profesyonel keskinleştirme."""
    return img_pil.filter(ImageFilter.UnsharpMask(
        radius=radius,
        percent=percent,
        threshold=threshold
    ))

def enhance_colors(img_pil, saturation=1.25, contrast=1.15, brightness=1.05):
    """Renk canlandırma — saturation + contrast + brightness."""
    img = ImageEnhance.Color(img_pil).enhance(saturation)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Brightness(img).enhance(brightness)
    return img

def edge_enhance(img_np):
    """Kenar keskinleştirme — detail recovery."""
    # LAB renk uzayında L kanalına bilateral filter
    lab = cv2.cvtColor(img_np, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    # CLAHE — Contrast Limited Adaptive Histogram Equalization
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l)
    lab_enhanced = cv2.merge([l_enhanced, a, b])
    return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

def iterative_upscale(img_pil, target_scale, max_step=2.0):
    """
    Büyük scale'leri adım adım yap (2x2x = 4x).
    Direkt 4x yerine 2x → 2x daha kaliteli sonuç verir.
    """
    remaining = target_scale
    current = img_pil
    while remaining > 1.01:
        step = min(remaining, max_step)
        current = upscale_lanczos(current, step)
        # Her adımda hafif sharpen
        if step >= 1.5:
            current = sharpen_unsharp_mask(current, radius=1.5, percent=120, threshold=2)
        remaining /= step
    return current

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
    """
    Ana upscale fonksiyonu.
    Returns: (output_bytes, stats_dict)
    """
    t0 = time.time()

    # Bytes → numpy
    arr = np.frombuffer(image_bytes, np.uint8)
    img_np = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_np is None:
        raise ValueError("Geçersiz görüntü formatı")

    # Analiz
    info = analyze_image(img_np)
    orig_w, orig_h = info['width'], info['height']

    # Max output boyutu kısıtla
    target_w = orig_w * scale
    target_h = orig_h * scale
    if max(target_w, target_h) > max_output_px:
        limit_scale = max_output_px / max(target_w, target_h)
        scale = scale * limit_scale

    # Adım 1: Gürültü gider (önce, upscale'den önce daha etkili)
    if info['is_noisy'] and denoise_strength > 0:
        img_np = denoise(img_np, denoise_strength)

    # Adım 2: Edge/detail enhancement
    img_np = edge_enhance(img_np)

    # Adım 3: numpy → PIL
    img_rgb = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)

    # Adım 4: Iterative upscale (Lanczos)
    img_up = iterative_upscale(img_pil, scale, max_step=2.0)

    # Adım 5: Final sharpen
    if sharpen_amount > 0:
        img_up = sharpen_unsharp_mask(
            img_up,
            radius=2.0,
            percent=sharpen_amount,
            threshold=3
        )

    # Adım 6: Renk geliştir
    img_up = enhance_colors(img_up, enhance_sat, enhance_contrast)

    # Adım 7: Output
    out_buf = io.BytesIO()
    final_w, final_h = img_up.size
    if output_format.upper() == 'JPEG':
        img_up = img_up.convert('RGB')
        img_up.save(out_buf, format='JPEG', quality=97, subsampling=0)
        mime = 'image/jpeg'
        ext = 'jpg'
    elif output_format.upper() == 'WEBP':
        img_up.save(out_buf, format='WEBP', quality=95, method=6)
        mime = 'image/webp'
        ext = 'webp'
    else:
        img_up.save(out_buf, format='PNG', optimize=False, compress_level=1)
        mime = 'image/png'
        ext = 'png'

    out_bytes = out_buf.getvalue()
    elapsed = time.time() - t0

    stats = {
        'original_w': orig_w,
        'original_h': orig_h,
        'output_w': final_w,
        'output_h': final_h,
        'actual_scale': round(final_w / orig_w, 2),
        'original_kb': len(image_bytes) // 1024,
        'output_kb': len(out_bytes) // 1024,
        'elapsed_sec': round(elapsed, 2),
        'was_blurry': info['is_blurry'],
        'was_noisy': info['is_noisy'],
        'sharpness_score': round(info['sharpness'], 1),
        'mime': mime,
        'ext': ext,
    }
    return out_bytes, stats
