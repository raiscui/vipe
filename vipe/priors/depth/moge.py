# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import torch


try:
    from moge.model.v1 import MoGeModel as MoGeModelV1
except ModuleNotFoundError:
    MoGeModelV1 = None

try:
    from moge.model.v2 import MoGeModel as MoGeModelV2
except ModuleNotFoundError:
    MoGeModelV2 = None

from vipe.utils.misc import unpack_optional
from vipe.utils.cameras import CameraType

from .base import DepthEstimationInput, DepthEstimationModel, DepthEstimationResult, DepthType


def focal_length_to_fov_degrees(focal_length: float, image_width: float) -> float:
    """Compute horizontal field of view from focal length."""
    fov_rad = 2 * torch.atan(torch.tensor(image_width / (2 * focal_length)))
    fov_deg = torch.rad2deg(fov_rad)
    return fov_deg.item()


def _normalize_moge_version(version: str) -> str:
    """把用户输入的 version 归一化为 v1/v2.

    说明:
    - 配置层我们用 `moge-v2`/`moge-v1` 来表达选择.
    - 兼容历史写法 `moge`(version 为空),默认认为是 v2.
    """

    v = (version or "").strip().lower()
    if v in {"", "v2", "2", "latest"}:
        return "v2"
    if v in {"v1", "1"}:
        return "v1"
    raise ValueError(f"Unknown MoGe version: {version}. Use `moge-v2` or `moge-v1`.")


class MogeModel(DepthEstimationModel):
    """https://github.com/microsoft/MoGe"""

    def __init__(self, version: str = "") -> None:
        super().__init__()
        moge_version = _normalize_moge_version(version)

        # ---------------------------------------------------------------------
        # MoGe 版本选择
        # ---------------------------------------------------------------------
        #
        # 背景:
        # - MoGe 有 v1/v2 两套模型结构,对应不同的 checkpoint.
        # - 如果用 v1 的 `MoGeModel` 去加载 v2 的权重,会在内部配置解析阶段崩溃(lyra 已踩过).
        # - 因此这里显式按版本选择对应实现,并在配置层允许切换.
        #
        if moge_version == "v2":
            if MoGeModelV2 is None:
                raise RuntimeError(
                    "moge(v2) is not found in the environment. Please install MoGe via `pip install git+https://github.com/microsoft/MoGe.git`."
                )
            model_cls = MoGeModelV2
            model_id = "Ruicheng/moge-2-vitl"
        else:
            if MoGeModelV1 is None:
                raise RuntimeError(
                    "moge(v1) is not found in the environment. Please install MoGe via `pip install git+https://github.com/microsoft/MoGe.git`."
                )
            model_cls = MoGeModelV1
            model_id = "Ruicheng/moge-vitl"

        self.moge_version = moge_version
        self.model_id = model_id

        # 模型权重会由 huggingface-hub 自动缓存.
        # 我们在这里不做额外的"预下载"操作,避免在代理环境下浪费流量.
        self.model = model_cls.from_pretrained(model_id)
        self.model = self.model.cuda().eval()

    @property
    def depth_type(self) -> DepthType:
        return DepthType.MODEL_METRIC_DEPTH

    def estimate(self, src: DepthEstimationInput) -> DepthEstimationResult:
        rgb: torch.Tensor = unpack_optional(src.rgb)
        assert rgb.dtype == torch.float32, "Input image should be float32"
        assert src.camera_type == CameraType.PINHOLE, "MoGe only supports pinhole cameras"

        focal_length: float = unpack_optional(src.intrinsics)[0].item()

        if rgb.dim() == 3:
            rgb, batch_dim = rgb[None], False
        else:
            batch_dim = True

        w = rgb.shape[2]
        input_image_for_depth = rgb.moveaxis(-1, 1)

        # MoGe inference
        moge_input_dict = {"fov_x": focal_length_to_fov_degrees(focal_length, w)}

        with torch.no_grad():
            moge_output_full = self.model.infer(input_image_for_depth, **moge_input_dict)

        moge_depth_hw_full = moge_output_full["depth"]
        moge_mask_hw_full = moge_output_full["mask"]

        # Process depth
        moge_depth_tensor = torch.nan_to_num(moge_depth_hw_full, nan=1e4)
        moge_depth_tensor = torch.clamp(moge_depth_tensor, min=0, max=1e4)

        moge_depth_tensor = moge_depth_tensor * moge_mask_hw_full.float()

        if not batch_dim:
            moge_depth_tensor = moge_depth_tensor.squeeze(0)
            moge_mask_hw_full = moge_mask_hw_full.squeeze(0)

        return DepthEstimationResult(metric_depth=moge_depth_tensor)
