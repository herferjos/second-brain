"""Local OCR using LightOnOCR-2-1B via Transformers (no API key)."""
import base64
import io
import os
from pathlib import Path

import torch
from PIL import Image
from transformers import LightOnOcrForConditionalGeneration, LightOnOcrProcessor

MODEL_ID = "lightonai/LightOnOCR-2-1B"
MAX_NEW_TOKENS = int(os.getenv("FRAME_CAPTURE_MAX_NEW_TOKENS", "1024"))
MAX_IMAGE_SIZE = int(os.getenv("FRAME_CAPTURE_MAX_IMAGE_SIZE", "1540"))


def _device_dtype():
    if torch.backends.mps.is_available():
        return "mps", torch.float32
    if torch.cuda.is_available():
        return "cuda", torch.bfloat16
    return "cpu", torch.float32


def _resize_longest(image: Image.Image, max_size: int) -> Image.Image:
    w, h = image.size
    if max(w, h) <= max_size:
        return image
    if w > h:
        nw, nh = max_size, int(h * max_size / w)
    else:
        nw, nh = int(w * max_size / h), max_size
    return image.resize((nw, nh), Image.Resampling.LANCZOS)


def _image_to_data_uri(pil_img: Image.Image) -> str:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def load_ocr_model():
    """Load model and processor once. Returns (model, processor, device, dtype)."""
    device, dtype = _device_dtype()
    model = LightOnOcrForConditionalGeneration.from_pretrained(
        MODEL_ID,
        torch_dtype=dtype,
        trust_remote_code=True,
    ).to(device)
    processor = LightOnOcrProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    return model, processor, device, dtype


def ocr_image_to_markdown(
    model,
    processor,
    device: str,
    dtype: torch.dtype,
    image_path: Path,
) -> str:
    """Run OCR on a local image file; returns markdown text."""
    pil_img = Image.open(image_path).convert("RGB")
    pil_img = _resize_longest(pil_img, MAX_IMAGE_SIZE)
    image_url = _image_to_data_uri(pil_img)

    conversation = [
        {"role": "user", "content": [{"type": "image", "url": image_url}]}
    ]

    inputs = processor.apply_chat_template(
        conversation,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = {
        k: v.to(device=device, dtype=dtype) if v.is_floating_point() else v.to(device)
        for k, v in inputs.items()
    }

    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)

    generated_ids = output_ids[0, inputs["input_ids"].shape[1] :]
    return processor.decode(generated_ids, skip_special_tokens=True)
