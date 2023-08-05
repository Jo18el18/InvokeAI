# Copyright (c) 2022 Kyle Schouviller (https://github.com/kyle0654)

from typing import Literal, Optional

import numpy
from PIL import Image, ImageFilter, ImageOps, ImageChops
from pydantic import Field
from pathlib import Path
from typing import Union
from invokeai.app.invocations.metadata import CoreMetadata
from ..models.image import (
    ImageCategory,
    ImageField,
    ResourceOrigin,
    ImageOutput,
    MaskOutput,
)
from .baseinvocation import (
    BaseInvocation,
    InvocationContext,
    UINodeConfig,
    UIInputField,
)
from invokeai.backend.image_util.safety_checker import SafetyChecker
from invokeai.backend.image_util.invisible_watermark import InvisibleWatermark


class LoadImageInvocation(BaseInvocation):
    """Load an image and provide it as output."""

    type: Literal["load_image"] = "load_image"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to load")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Load Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    )
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        return ImageOutput(
            image=ImageField(image_name=self.image.image_name),
            width=image.width,
            height=image.height,
        )


class ShowImageInvocation(BaseInvocation):
    """Displays a provided image, and passes it forward in the pipeline."""

    type: Literal["show_image"] = "show_image"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to show")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Show Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    )
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)
        if image:
            image.show()

        # TODO: how to handle failure?

        return ImageOutput(
            image=ImageField(image_name=self.image.image_name),
            width=image.width,
            height=image.height,
        )


class ImageCropInvocation(BaseInvocation):
    """Crops an image to a specified box. The box can be outside of the image."""

    type: Literal["img_crop"] = "img_crop"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to crop")
    x: int = Field(default=0, description="The left x coordinate of the crop rectangle")
    y: int = Field(default=0, description="The top y coordinate of the crop rectangle")
    width: int = Field(default=512, gt=0, description="The width of the crop rectangle")
    height: int = Field(default=512, gt=0, description="The height of the crop rectangle")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Crop Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    )
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        image_crop = Image.new(mode="RGBA", size=(self.width, self.height), color=(0, 0, 0, 0))
        image_crop.paste(image, (-self.x, -self.y))

        image_dto = context.services.images.create(
            image=image_crop,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class ImagePasteInvocation(BaseInvocation):
    """Pastes an image into another image."""

    type: Literal["img_paste"] = "img_paste"

    # Inputs
    base_image: Optional[ImageField] = Field(default=None, description="The base image")
    image: Optional[ImageField] = Field(default=None, description="The image to paste")
    mask: Optional[ImageField] = Field(default=None, description="The mask to use when pasting")
    x: int = Field(default=0, description="The left x coordinate at which to paste the image")
    y: int = Field(default=0, description="The top y coordinate at which to paste the image")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Paste Image",
                tags=[
                    "image",
                ],
                fields={
                    "base_image": UIInputField(
                        input_requirement="required",
                    ),
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                    "mask": UIInputField(
                        input_requirement="optional",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        base_image = context.services.images.get_pil_image(self.base_image.image_name)
        image = context.services.images.get_pil_image(self.image.image_name)
        mask = (
            None if self.mask is None else ImageOps.invert(context.services.images.get_pil_image(self.mask.image_name))
        )
        # TODO: probably shouldn't invert mask here... should user be required to do it?

        min_x = min(0, self.x)
        min_y = min(0, self.y)
        max_x = max(base_image.width, image.width + self.x)
        max_y = max(base_image.height, image.height + self.y)

        new_image = Image.new(mode="RGBA", size=(max_x - min_x, max_y - min_y), color=(0, 0, 0, 0))
        new_image.paste(base_image, (abs(min_x), abs(min_y)))
        new_image.paste(image, (max(0, self.x), max(0, self.y)), mask=mask)

        image_dto = context.services.images.create(
            image=new_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class MaskFromAlphaInvocation(BaseInvocation):
    """Extracts the alpha channel of an image as a mask."""

    type: Literal["tomask"] = "tomask"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to create the mask from")
    invert: bool = Field(default=False, description="Whether or not to invert the mask")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Mask from Alpha",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    )
                },
            )
        }

    def invoke(self, context: InvocationContext) -> MaskOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        image_mask = image.split()[-1]
        if self.invert:
            image_mask = ImageOps.invert(image_mask)

        image_dto = context.services.images.create(
            image=image_mask,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.MASK,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return MaskOutput(
            mask=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class ImageMultiplyInvocation(BaseInvocation):
    """Multiplies two images together using `PIL.ImageChops.multiply()`."""

    type: Literal["img_mul"] = "img_mul"

    # Inputs
    image1: Optional[ImageField] = Field(default=None, description="The first image to multiply")
    image2: Optional[ImageField] = Field(default=None, description="The second image to multiply")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Multiply Images",
                tags=[
                    "image",
                ],
                fields={
                    "image1": UIInputField(
                        input_requirement="required",
                    ),
                    "image2": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image1 = context.services.images.get_pil_image(self.image1.image_name)
        image2 = context.services.images.get_pil_image(self.image2.image_name)

        multiply_image = ImageChops.multiply(image1, image2)

        image_dto = context.services.images.create(
            image=multiply_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


IMAGE_CHANNELS = Literal["A", "R", "G", "B"]


class ImageChannelInvocation(BaseInvocation):
    """Gets a channel from an image."""

    type: Literal["img_chan"] = "img_chan"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to get the channel from")
    channel: IMAGE_CHANNELS = Field(default="A", description="The channel to get")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Extract Image Channel",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        channel_image = image.getchannel(self.channel)

        image_dto = context.services.images.create(
            image=channel_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


IMAGE_MODES = Literal["L", "RGB", "RGBA", "CMYK", "YCbCr", "LAB", "HSV", "I", "F"]


class ImageConvertInvocation(BaseInvocation):
    """Converts an image to a different mode."""

    type: Literal["img_conv"] = "img_conv"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to convert")
    mode: IMAGE_MODES = Field(default="L", description="The mode to convert to")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Convert Image Mode",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        converted_image = image.convert(self.mode)

        image_dto = context.services.images.create(
            image=converted_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class ImageBlurInvocation(BaseInvocation):
    """Blurs an image"""

    type: Literal["img_blur"] = "img_blur"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to blur")
    radius: float = Field(default=8.0, ge=0, description="The blur radius")
    blur_type: Literal["gaussian", "box"] = Field(default="gaussian", description="The type of blur")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Blur Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        blur = (
            ImageFilter.GaussianBlur(self.radius) if self.blur_type == "gaussian" else ImageFilter.BoxBlur(self.radius)
        )
        blur_image = image.filter(blur)

        image_dto = context.services.images.create(
            image=blur_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


PIL_RESAMPLING_MODES = Literal[
    "nearest",
    "box",
    "bilinear",
    "hamming",
    "bicubic",
    "lanczos",
]


PIL_RESAMPLING_MAP = {
    "nearest": Image.Resampling.NEAREST,
    "box": Image.Resampling.BOX,
    "bilinear": Image.Resampling.BILINEAR,
    "hamming": Image.Resampling.HAMMING,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
}


class ImageResizeInvocation(BaseInvocation):
    """Resizes an image to specific dimensions"""

    type: Literal["img_resize"] = "img_resize"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to resize")
    width: Union[int, None] = Field(ge=64, multiple_of=8, description="The width to resize to (px)")
    height: Union[int, None] = Field(ge=64, multiple_of=8, description="The height to resize to (px)")
    resample_mode: PIL_RESAMPLING_MODES = Field(default="bicubic", description="The resampling mode")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Resize Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                    "width": UIInputField(
                        input_requirement="required",
                    ),
                    "height": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        resample_mode = PIL_RESAMPLING_MAP[self.resample_mode]

        resize_image = image.resize(
            (self.width, self.height),
            resample=resample_mode,
        )

        image_dto = context.services.images.create(
            image=resize_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class ImageScaleInvocation(BaseInvocation):
    """Scales an image by a factor"""

    type: Literal["img_scale"] = "img_scale"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to scale")
    scale_factor: Optional[float] = Field(default=2.0, gt=0, description="The factor by which to scale the image")
    resample_mode: PIL_RESAMPLING_MODES = Field(default="bicubic", description="The resampling mode")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Scale Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                    "scale": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        resample_mode = PIL_RESAMPLING_MAP[self.resample_mode]
        width = int(image.width * self.scale_factor)
        height = int(image.height * self.scale_factor)

        resize_image = image.resize(
            (width, height),
            resample=resample_mode,
        )

        image_dto = context.services.images.create(
            image=resize_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class ImageLerpInvocation(BaseInvocation):
    """Linear interpolation of all pixels of an image"""

    # fmt: off
    type: Literal["img_lerp"] = "img_lerp"

    # Inputs
    image: Optional[ImageField]  = Field(default=None, description="The image to lerp")
    min: int = Field(default=0, ge=0, le=255, description="The minimum output value")
    max: int = Field(default=255, ge=0, le=255, description="The maximum output value")
    # fmt: on

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Lerp Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        image_arr = numpy.asarray(image, dtype=numpy.float32) / 255
        image_arr = image_arr * (self.max - self.min) + self.max

        lerp_image = Image.fromarray(numpy.uint8(image_arr))

        image_dto = context.services.images.create(
            image=lerp_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class ImageInverseLerpInvocation(BaseInvocation):
    """Inverse linear interpolation of all pixels of an image"""

    type: Literal["img_ilerp"] = "img_ilerp"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to lerp")
    min: int = Field(default=0, ge=0, le=255, description="The minimum input value")
    max: int = Field(default=255, ge=0, le=255, description="The maximum input value")

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Inverse Lerp Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        image_arr = numpy.asarray(image, dtype=numpy.float32)
        image_arr = numpy.minimum(numpy.maximum(image_arr - self.min, 0) / float(self.max - self.min), 1) * 255

        ilerp_image = Image.fromarray(numpy.uint8(image_arr))

        image_dto = context.services.images.create(
            image=ilerp_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )


class ImageNSFWBlurInvocation(BaseInvocation):
    """Add blur to NSFW-flagged images"""

    type: Literal["img_nsfw"] = "img_nsfw"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to check")
    metadata: Optional[CoreMetadata] = Field(
        default=None, description="Optional core metadata to be written to the image"
    )

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Blur NSFW Image",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                    "metadata": UIInputField(hidden=True),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)

        logger = context.services.logger
        logger.debug("Running NSFW checker")
        if SafetyChecker.has_nsfw_concept(image):
            logger.info("A potentially NSFW image has been detected. Image will be blurred.")
            blurry_image = image.filter(filter=ImageFilter.GaussianBlur(radius=32))
            caution = self._get_caution_img()
            blurry_image.paste(caution, (0, 0), caution)
            image = blurry_image

        image_dto = context.services.images.create(
            image=image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
            metadata=self.metadata.dict() if self.metadata else None,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )

    def _get_caution_img(self) -> Image:
        import invokeai.app.assets.images as image_assets

        caution = Image.open(Path(image_assets.__path__[0]) / "caution.png")
        return caution.resize((caution.width // 2, caution.height // 2))


class ImageWatermarkInvocation(BaseInvocation):
    """Add an invisible watermark to an image"""

    type: Literal["img_watermark"] = "img_watermark"

    # Inputs
    image: Optional[ImageField] = Field(default=None, description="The image to check")
    text: str = Field(default="InvokeAI", description="Watermark text")
    metadata: Optional[CoreMetadata] = Field(
        default=None, description="Optional core metadata to be written to the image"
    )

    # Schema Customisation
    class Config:
        schema_extra = {
            "ui": UINodeConfig(
                title="Add Invisible Watermark",
                tags=[
                    "image",
                ],
                fields={
                    "image": UIInputField(
                        input_requirement="required",
                    ),
                    "metadata": UIInputField(hidden=True),
                },
            )
        }

    def invoke(self, context: InvocationContext) -> ImageOutput:
        image = context.services.images.get_pil_image(self.image.image_name)
        new_image = InvisibleWatermark.add_watermark(image, self.text)
        image_dto = context.services.images.create(
            image=new_image,
            image_origin=ResourceOrigin.INTERNAL,
            image_category=ImageCategory.GENERAL,
            node_id=self.id,
            session_id=context.graph_execution_state_id,
            is_intermediate=self.is_intermediate,
            metadata=self.metadata.dict() if self.metadata else None,
        )

        return ImageOutput(
            image=ImageField(image_name=image_dto.image_name),
            width=image_dto.width,
            height=image_dto.height,
        )
