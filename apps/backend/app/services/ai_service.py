import face_recognition
import numpy as np
from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError
import logging

logger = logging.getLogger(__name__)

MAX_IMAGE_DIMENSION = 1000
FACE_MATCH_DISTANCE_THRESHOLD = 0.6


def get_face_encodings(image_content: bytes):
    try:
        image = Image.open(BytesIO(image_content))

        image = ImageOps.exif_transpose(image)

        if image.mode != "RGB":
            image = image.convert("RGB")

        if max(image.size) > MAX_IMAGE_DIMENSION:
            logger.info(f"Resizing large image: {image.size} -> max {MAX_IMAGE_DIMENSION}")
            image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

        image_np = np.array(image)

        # Use num_jitters=1 (default) and standard model, the resizing is the main speedup
        return face_recognition.face_encodings(image_np)

    except UnidentifiedImageError:
        logger.warning("Failed to load image: invalid format")
        return []
    except Exception as e:
        logger.error(f"Error in face encoding: {str(e)}")
        return []


def compare_faces(known_encoding: np.ndarray, unknown_encoding: np.ndarray) -> bool:
    try:
        distances = face_recognition.face_distance([known_encoding], unknown_encoding)
        return bool(distances[0] < FACE_MATCH_DISTANCE_THRESHOLD)
    except Exception as e:
        logger.error(f"Error comparing faces: {str(e)}")
        return False
