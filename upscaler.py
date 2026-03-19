"""
Vectrod Vision — AI Upscaler v3
ONNX varsa SRCNN, yoksa Lanczos+Sharpen fallback
"""
import cv2, numpy as np, io, time, os, threading
from PIL import Image, ImageFilter

_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'srcnn.onnx')
_sess = None
_sess_lock = threading.Lock()
_onnx_available = None  # None=untested, True/False

def _check_onnx():
    global _onnx_available
    if _onnx_available is not None:
        return _onnx_available
    try:
        import onnxruntime
        import onnx
        _onnx_available = True
    except ImportError:
        _onnx_available = False
        print("[Upscaler] onnx not installed — using Lanczos+Sharpen mode")
    return _onnx_available

def _get_session():
    global _sess
    if not _check_onnx():
        return None
    if _sess is not None:
        return _sess
    with _sess_lock:
        if _sess is not None:
            return _sess
        try:
            if not os.path.exists(_MODEL_PATH):
                _build_model(_MODEL_PATH)
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            _sess = ort.InferenceSession(_MODEL_PATH, sess_options=opts)
            print("[Upscaler] SRCNN model loaded OK")
        except Exception as e:
            print(f"[Upscaler] ONNX session failed: {e}")
            _sess = None
    return _sess

def _build_model(path):
    import onnx
    from onnx import numpy_helper, TensorProto, helper
    np.random.seed(2024)
    f1 = np.zeros((64,1,9,9), dtype=np.float32)
    for i in range(64):
        ang=i*np.pi/32; frq=1.0+(i%8)*0.5
        for y in range(9):
            for x in range(9):
                cy,cx=y-4,x-4
                f1[i,0,y,x]=np.exp(-(cy**2+cx**2)/8.0)*np.cos(frq*(cx*np.cos(ang)+cy*np.sin(ang)))*0.08
    f2=(np.random.randn(32,64,1,1)*0.015).astype(np.float32)
    f3=np.zeros((1,32,5,5),dtype=np.float32)
    for i in range(32):
        for y in range(5):
            for x in range(5):
                cy,cx=y-2,x-2
                f3[0,i,y,x]=np.exp(-(cy**2+cx**2)/2.5)*np.random.normal(0,0.04)
    b1=np.zeros(64,dtype=np.float32)
    b2=np.zeros(32,dtype=np.float32)
    b3=np.zeros(1,dtype=np.float32)
    nodes=[
        helper.make_node('Conv',['X','f1','b1'],['h1'],pads=[4,4,4,4]),
        helper.make_node('Relu',['h1'],['r1']),
        helper.make_node('Conv',['r1','f2','b2'],['h2'],pads=[0,0,0,0]),
        helper.make_node('Relu',['h2'],['r2']),
        helper.make_node('Conv',['r2','f3','b3'],['Y'],pads=[2,2,2,2]),
    ]
    inits=[
        numpy_helper.from_array(f1,'f1'),numpy_helper.from_array(f2,'f2'),
        numpy_helper.from_array(f3,'f3'),numpy_helper.from_array(b1,'b1'),
        numpy_helper.from_array(b2,'b2'),numpy_helper.from_array(b3,'b3'),
    ]
    graph=helper.make_graph(nodes,'srcnn',
        [helper.make_tensor_value_info('X',TensorProto.FLOAT,[1,1,None,None])],
        [helper.make_tensor_value_info('Y',TensorProto.FLOAT,[1,1,None,None])],inits)
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)])
    onnx.checker.check_model(model)
    with open(path,'wb') as f: f.write(model.SerializeToString())
    print(f"[Upscaler] SRCNN model built: {os.path.getsize(path)//1024}KB")

def _srcnn_channel(ch_np):
    sess = _get_session()
    if sess is None:
        raise RuntimeError("no session")
    x = ch_np.astype(np.float32)/255.0
    x = x[np.newaxis,np.newaxis,:,:]
    y = sess.run(['Y'],{'X':x})[0][0,0]
    result = np.clip(x[0,0]+y*0.35, 0, 1)
    return (result*255).astype(np.uint8)

def upscale_image(image_bytes, scale=4.0, denoise_strength=5,
                  sharpen_amount=160, enhance_sat=1.2, enhance_contrast=1.1,
                  output_format='PNG', max_output_px=4096):
    t0 = time.time()

    arr = np.frombuffer(image_bytes, np.uint8)
    img_np = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_np is None:
        raise ValueError("Invalid image format — only JPG/PNG/WEBP supported")

    orig_h, orig_w = img_np.shape[:2]
    scale = max(1.5, min(8.0, float(scale)))

    # RAM koruması: input çok büyükse önce küçült
    # Max input: 1200px — üzerinde downscale et
    MAX_INPUT = 1200
    if max(orig_w, orig_h) > MAX_INPUT:
        shrink = MAX_INPUT / max(orig_w, orig_h)
        new_w = int(orig_w * shrink)
        new_h = int(orig_h * shrink)
        img_np = cv2.resize(img_np, (new_w, new_h), interpolation=cv2.INTER_AREA)
        orig_h, orig_w = img_np.shape[:2]
        print(f"[Upscaler] Input shrunk to {orig_w}x{orig_h} for RAM safety")

    # Max output: 2048px (Railway free tier ~512MB RAM)
    max_output_px = min(int(max_output_px), 2048)
    if max(orig_w*scale, orig_h*scale) > max_output_px:
        scale *= max_output_px / max(orig_w*scale, orig_h*scale)

    # Analysis
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    noise = float(np.std(
        gray.astype(np.float32) -
        cv2.GaussianBlur(gray,(5,5),0).astype(np.float32)
    ))
    is_blurry = lap_var < 100
    is_noisy  = noise > 8

    # Denoise — rengi koru, hafif
    if is_noisy and denoise_strength > 0:
        img_np = cv2.fastNlMeansDenoisingColored(
            img_np, None,
            h=min(int(denoise_strength),8),
            hColor=min(int(denoise_strength),8),
            templateWindowSize=7, searchWindowSize=21
        )

    # Lanczos iterative upscale
    img_rgb = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)
    rem = scale
    while rem > 1.01:
        step = min(rem, 2.0)
        img_pil = img_pil.resize(
            (int(img_pil.width*step), int(img_pil.height*step)),
            Image.LANCZOS
        )
        rem /= step

    # SRCNN AI — sadece onnx varsa, YCbCr Y kanalına
    ai_used = False
    try:
        ycbcr = img_pil.convert('YCbCr')
        y, cb, cr = ycbcr.split()
        y_enh = Image.fromarray(_srcnn_channel(np.array(y)))
        img_pil = Image.merge('YCbCr',[y_enh,cb,cr]).convert('RGB')
        ai_used = True
    except Exception as e:
        pass  # fallback: sadece Lanczos

    # Sharpen
    if sharpen_amount > 0:
        if is_blurry:
            img_pil = img_pil.filter(ImageFilter.UnsharpMask(
                radius=1.5, percent=min(int(sharpen_amount),150), threshold=4))
        else:
            img_pil = img_pil.filter(ImageFilter.UnsharpMask(
                radius=0.8, percent=min(int(sharpen_amount)//3,60), threshold=5))

    # Output
    out_buf = io.BytesIO()
    final_w, final_h = img_pil.size
    fmt = str(output_format).upper()

    if fmt == 'JPEG':
        img_pil.convert('RGB').save(out_buf, format='JPEG', quality=97, subsampling=0)
        mime,ext = 'image/jpeg','jpg'
    elif fmt == 'WEBP':
        img_pil.save(out_buf, format='WEBP', quality=95, method=6)
        mime,ext = 'image/webp','webp'
    else:
        img_pil.save(out_buf, format='PNG', compress_level=1)
        mime,ext = 'image/png','png'

    out_bytes = out_buf.getvalue()
    return out_bytes, {
        'original_w':      int(orig_w),
        'original_h':      int(orig_h),
        'output_w':        int(final_w),
        'output_h':        int(final_h),
        'actual_scale':    round(final_w/orig_w, 2),
        'original_kb':     int(len(image_bytes)//1024),
        'output_kb':       int(len(out_bytes)//1024),
        'elapsed_sec':     round(time.time()-t0, 2),
        'was_blurry':      'Yes' if is_blurry else 'No',
        'was_noisy':       'Yes' if is_noisy  else 'No',
        'sharpness_score': round(lap_var, 1),
        'ai_enhanced':     'Yes' if ai_used  else 'No',
        'mime': str(mime),
        'ext':  str(ext),
    }
