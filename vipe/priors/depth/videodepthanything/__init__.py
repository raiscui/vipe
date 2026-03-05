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

import logging
import os
import urllib.parse

import numpy as np
import torch

from vipe.utils.misc import unpack_optional

from ..base import DepthEstimationInput, DepthEstimationModel, DepthEstimationResult, DepthType
from .video_depth import VideoDepthAnything


logger = logging.getLogger(__name__)


def _is_corrupted_checkpoint_error(exc: BaseException) -> bool:
    """判断是不是"权重文件损坏/下载不完整"导致的加载失败.

    说明:
    - 这类错误在网络不稳定或进程被中断时很常见(缓存落盘后不完整).
    - 我们只在非常明确的"文件格式损坏"特征上触发自动清理与重试,
      避免把真正的模型兼容性问题(例如 key/shape 不匹配)误判成缓存损坏.
    """

    msg = str(exc)
    return (
        "PytorchStreamReader failed reading zip archive" in msg
        or "failed finding central directory" in msg
        or "unexpected EOF" in msg
    )


def _torch_load_state_dict(path: str) -> dict:
    """更安全地加载 state_dict.

    - torch>=2.0 支持 `weights_only=True`,可避免不必要的 pickle 反序列化风险.
    - 为了兼容旧 torch,这里做一次降级.
    """

    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


def _load_state_dict_from_hf(repo_id: str, filename: str) -> dict:
    """从 Hugging Face Hub 下载并加载权重.

    为什么不用 `torch.hub.load_state_dict_from_url`:
    - torch.hub 使用 urllib 下载,在代理/网络抖动场景下更容易留下不完整缓存文件.
    - huggingface_hub 自带更稳的缓存与下载逻辑(包含原子写入/断点续传等机制),
      更适合从 HF 拉取大权重.
    """

    # ---------------------------------------------------------------------
    # 省流量优先: 先尝试复用 torch.hub 的本地缓存
    # ---------------------------------------------------------------------
    #
    # 背景:
    # - 历史版本用 `torch.hub.load_state_dict_from_url` 下载权重,文件会落在:
    #   ~/.cache/torch/hub/checkpoints/<filename>
    # - 直接切到 huggingface_hub 会导致"已有缓存也重新下载",浪费流量.
    # - 因此我们先尝试读 torch.hub 的缓存,失败再走 HF 的下载与缓存体系.
    #
    torch_hub_cached_path = os.path.join(torch.hub.get_dir(), "checkpoints", filename)
    if os.path.exists(torch_hub_cached_path):
        try:
            return _torch_load_state_dict(torch_hub_cached_path)
        except Exception as exc:
            # 损坏缓存: 删除后再走 HF 下载,避免每次都踩同一个坏文件
            if _is_corrupted_checkpoint_error(exc):
                logger.warning("检测到 torch.hub 权重缓存损坏,将删除并改用 HF 下载: %s", torch_hub_cached_path)
                try:
                    os.remove(torch_hub_cached_path)
                except OSError:
                    pass
            else:
                # 其它错误: 不强删,但仍然尝试从 HF 重新获取一份,避免卡死在坏缓存上
                logger.warning(
                    "读取 torch.hub 缓存失败,将回退到 HF 下载: path=%s err=%s",
                    torch_hub_cached_path,
                    exc,
                )

    try:
        from huggingface_hub import hf_hub_download
    except ModuleNotFoundError:
        # 理论上不会发生: 本项目依赖 transformers,因此应当自带 huggingface_hub.
        # 这里保留降级路径,避免极简环境直接崩掉.
        raise RuntimeError("huggingface_hub is required to download Video-Depth-Anything checkpoints.")

    ckpt_path = hf_hub_download(repo_id=repo_id, filename=filename)
    try:
        return _torch_load_state_dict(ckpt_path)
    except Exception as exc:
        if not _is_corrupted_checkpoint_error(exc):
            raise

        # 缓存文件损坏时,强制重下 1 次(避免用户手工清缓存).
        logger.warning(
            "检测到 Video-Depth-Anything 权重缓存可能损坏,将强制重新下载: repo_id=%s filename=%s path=%s",
            repo_id,
            filename,
            ckpt_path,
        )
        ckpt_path = hf_hub_download(repo_id=repo_id, filename=filename, force_download=True)
        return _torch_load_state_dict(ckpt_path)


def _load_state_dict_from_url_with_retry(url: str) -> dict:
    """兼容兜底: 仍然用 torch.hub 下载,但在缓存损坏时自动清理并重试 1 次."""

    def _torch_hub_load() -> dict:
        try:
            return torch.hub.load_state_dict_from_url(url, map_location="cpu", weights_only=True)
        except TypeError:
            # 兼容旧 torch(没有 weights_only 参数)
            return torch.hub.load_state_dict_from_url(url, map_location="cpu")

    try:
        return _torch_hub_load()
    except Exception as exc:
        if not _is_corrupted_checkpoint_error(exc):
            raise

        model_dir = os.path.join(torch.hub.get_dir(), "checkpoints")
        filename = os.path.basename(urllib.parse.urlparse(url).path)
        cached_path = os.path.join(model_dir, filename)
        if os.path.exists(cached_path):
            logger.warning("检测到 torch.hub 权重缓存损坏,将删除并重试下载: %s", cached_path)
            try:
                os.remove(cached_path)
            except OSError:
                # 删除失败时仍继续重试,让 torch.hub 自己报更明确的错误
                pass

        return _torch_hub_load()


class VideoDepthAnythingDepthModel(DepthEstimationModel):
    """
    https://github.com/DepthAnything/Video-Depth-Anything
    """

    def __init__(self, model: str = "vitl", input_size: int = 518) -> None:
        super().__init__()

        self.model_config = {
            "vits": {
                "encoder": "vits",
                "features": 64,
                "out_channels": [48, 96, 192, 384],
            },
            "vitl": {
                "encoder": "vitl",
                "features": 256,
                "out_channels": [256, 512, 1024, 1024],
            },
        }[model]

        self.is_metric = False
        if model == "vits":
            self.ckpt_repo_id = "depth-anything/Video-Depth-Anything-Small"
            self.ckpt_filename = "video_depth_anything_vits.pth"
            self.ckpt_url = f"https://huggingface.co/{self.ckpt_repo_id}/resolve/main/{self.ckpt_filename}"
            self.use_fp32 = True
        elif model == "vitl":
            self.ckpt_repo_id = "depth-anything/Video-Depth-Anything-Large"
            self.ckpt_filename = "video_depth_anything_vitl.pth"
            self.ckpt_url = f"https://huggingface.co/{self.ckpt_repo_id}/resolve/main/{self.ckpt_filename}"
            self.use_fp32 = False
        else:
            raise ValueError(f"Model {model} not supported")

        self.input_size = input_size

        self.model = VideoDepthAnything(**self.model_config)
        # 说明:
        # - 这里优先走 huggingface_hub 的缓存与下载逻辑,更稳.
        # - 如果未来极简环境缺少 huggingface_hub,再回退 torch.hub.
        try:
            state_dict = _load_state_dict_from_hf(self.ckpt_repo_id, self.ckpt_filename)
        except RuntimeError:
            # 降级: 避免因为下载工具不可用导致整个 pipeline 直接不可用
            state_dict = _load_state_dict_from_url_with_retry(self.ckpt_url)

        self.model.load_state_dict(
            state_dict,
            strict=True,
        )
        self.model.cuda().eval()

    @property
    def depth_type(self) -> DepthType:
        return DepthType.AFFINE_DISP

    def estimate(self, src: DepthEstimationInput) -> DepthEstimationResult:
        frame_list: list[np.ndarray] = unpack_optional(src.video_frame_list)
        depths = self.model.infer_video_depth(frame_list, input_size=self.input_size, fp32=self.use_fp32)  # [T, H, W]
        depths = torch.from_numpy(depths).float().cuda()
        return DepthEstimationResult(relative_inv_depth=depths)
