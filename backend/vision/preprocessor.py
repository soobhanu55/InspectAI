from PIL import Image
import io

def preprocess_image(file_bytes: bytes) -> Image.Image:
    """Load, validate, and normalize uploaded image."""
    image = Image.open(io.BytesIO(file_bytes))
    
    # Convert to RGB (handles PNG with alpha, CMYK, etc.)
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    # Validate size (reject tiny/corrupt images)
    if image.width < 64 or image.height < 64:
        raise ValueError("Image too small. Minimum 64x64 pixels.")
    
    return image
