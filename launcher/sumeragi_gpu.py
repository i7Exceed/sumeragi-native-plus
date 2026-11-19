#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Razz, i7Exceed.
"""Vulkan GPU enumeration, version checking, and selection for Sumeragi Native+."""

from __future__ import annotations

import collections
import ctypes
from typing import Any, Callable, List, Optional, Sequence, Tuple

# The game needs Vulkan 1.3 from the loader (vk_platform.cpp) and from the GPU it renders on
# (vk_instance.cpp; TargetVulkanApiVersion in vk_platform.h). Below that it stops before its first log
# line, or Windows does not start it at all (0xC0000139: basara4-core.exe imports Vulkan 1.1 loader functions).
VULKAN_REQUIRED = (1, 3)

# What vulkan-1.dll reported: loaded (False: no vulkan-1.dll), loader ((major, minor), None when the
# loader could not say), instance (a Vulkan instance could be made), devices [(name, deviceType,
# (major, minor))] in the loader's order, error (why the probe stopped part-way, "" when it did not).
VulkanProbe = collections.namedtuple(
    "VulkanProbe", "loaded loader instance devices error"
)


def vulkan_version(value: int) -> Tuple[int, int]:
    """(major, minor) of a packed Vulkan API version."""
    return ((value >> 22) & 0x7F, (value >> 12) & 0x3FF)


def probe_vulkan(load: Optional[Callable[[str], Any]] = None) -> VulkanProbe:
    """Ask vulkan-1.dll for its loader version and its GPUs (load: the DLL loader, for tests)."""
    try:
        vulkan = (load or ctypes.cdll.LoadLibrary)("vulkan-1.dll")
    except OSError as exc:
        return VulkanProbe(False, None, False, [], f"vulkan-1.dll: {exc}")
    loader, instance, devices = None, False, []
    try:
        enumerate_version = getattr(vulkan, "vkEnumerateInstanceVersion", None)
        if enumerate_version is None:
            loader = (1, 0)  # a Vulkan 1.0 loader has no vkEnumerateInstanceVersion
        else:
            enumerate_version.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
            enumerate_version.restype = ctypes.c_int32
            version = ctypes.c_uint32(0)
            if enumerate_version(ctypes.pointer(version)) == 0:
                loader = vulkan_version(version.value)

        class VkApplicationInfo(ctypes.Structure):
            _fields_ = [
                ("sType", ctypes.c_uint32),
                ("pNext", ctypes.c_void_p),
                ("pApplicationName", ctypes.c_char_p),
                ("applicationVersion", ctypes.c_uint32),
                ("pEngineName", ctypes.c_char_p),
                ("engineVersion", ctypes.c_uint32),
                ("apiVersion", ctypes.c_uint32),
            ]

        class VkInstanceCreateInfo(ctypes.Structure):
            _fields_ = [
                ("sType", ctypes.c_uint32),
                ("pNext", ctypes.c_void_p),
                ("flags", ctypes.c_uint32),
                ("pApplicationInfo", ctypes.POINTER(VkApplicationInfo)),
                ("enabledLayerCount", ctypes.c_uint32),
                ("ppEnabledLayerNames", ctypes.c_void_p),
                ("enabledExtensionCount", ctypes.c_uint32),
                ("ppEnabledExtensionNames", ctypes.c_void_p),
            ]

        class VkPhysicalDeviceProperties(ctypes.Structure):
            _fields_ = [
                ("apiVersion", ctypes.c_uint32),
                ("driverVersion", ctypes.c_uint32),
                ("vendorID", ctypes.c_uint32),
                ("deviceID", ctypes.c_uint32),
                ("deviceType", ctypes.c_uint32),
                ("deviceName", ctypes.c_char * 256),
                ("pipelineCacheUUID", ctypes.c_ubyte * 16),
                ("limits", ctypes.c_byte * 504),
                ("sparseProperties", ctypes.c_byte * 20),
            ]

        app_info = VkApplicationInfo(
            sType=1,
            pApplicationName=b"SumeragiLauncher",
            apiVersion=(1 << 22) | (2 << 12),
        )
        ci = VkInstanceCreateInfo(sType=2, pApplicationInfo=ctypes.pointer(app_info))
        vulkan.vkCreateInstance.argtypes = [
            ctypes.POINTER(VkInstanceCreateInfo),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        vulkan.vkCreateInstance.restype = ctypes.c_int32
        vulkan.vkDestroyInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        vulkan.vkEnumeratePhysicalDevices.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        vulkan.vkEnumeratePhysicalDevices.restype = ctypes.c_int32
        vulkan.vkGetPhysicalDeviceProperties.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(VkPhysicalDeviceProperties),
        ]

        inst = ctypes.c_void_p()
        if vulkan.vkCreateInstance(ctypes.pointer(ci), None, ctypes.pointer(inst)) == 0:
            instance = True
            count = ctypes.c_uint32(0)
            vulkan.vkEnumeratePhysicalDevices(inst, ctypes.pointer(count), None)
            if count.value > 0:
                devs = (ctypes.c_void_p * count.value)()
                vulkan.vkEnumeratePhysicalDevices(inst, ctypes.pointer(count), devs)
                for i in range(count.value):
                    p = VkPhysicalDeviceProperties()
                    vulkan.vkGetPhysicalDeviceProperties(devs[i], ctypes.pointer(p))
                    name = p.deviceName.decode("utf-8", errors="replace").strip("\x00")
                    devices.append((name, p.deviceType, vulkan_version(p.apiVersion)))
            vulkan.vkDestroyInstance(inst, None)
    except Exception as exc:
        return VulkanProbe(True, loader, instance, devices, f"{type(exc).__name__}: {exc}")
    return VulkanProbe(True, loader, instance, devices, "")


def gpu_choices(probe: VulkanProbe) -> List[Tuple[int, str, bool]]:
    """The Graphics card list: Auto, then each GPU as (index, display_name, is_discrete)."""
    gpus: List[Tuple[int, str, bool]] = [(-1, "Auto (Prioritaskan GPU Diskrit)", True)]
    for i, (name, kind, _api) in enumerate(probe.devices):
        is_disc = kind == 2
        kind_tag = "dGPU" if is_disc else ("iGPU" if kind == 1 else "GPU")
        gpus.append((i, f"GPU {i}: {name} ({kind_tag})", is_disc))
    return gpus


def game_gpu_id(
    gpu_index: int, gpus: Sequence[Tuple[int, str, bool]]
) -> Optional[int]:
    """The GPU the game is started on (SPARTAN_GPU_ID), or None to let the game choose: the user's
    choice, else for Auto the first discrete GPU."""
    if gpu_index != -1:
        return gpu_index
    return next((idx for idx, _, is_disc in gpus if is_disc and idx >= 0), None)


def vulkan_problem(probe: VulkanProbe, gpu_id: Optional[int] = None) -> Optional[str]:
    """Why the game will not start on this Vulkan, or None: "missing" (no vulkan-1.dll), "old" (the
    loader, or the GPU the game uses, is below VULKAN_REQUIRED) or "no_gpu" (no Vulkan GPU at all).
    gpu_id is game_gpu_id(): a GPU outside the list, or None, is the game's own choice, which takes a
    GPU with VULKAN_REQUIRED when there is one (vk_instance.cpp). A probe that stopped part-way gives
    None: nothing is certain then, and the warning must not stop a PC that works."""
    if not probe.loaded:
        return "missing"
    if probe.error:
        return None
    if probe.loader is not None and probe.loader < VULKAN_REQUIRED:
        return "old"
    if not probe.devices:
        return "no_gpu"
    if gpu_id is not None and 0 <= gpu_id < len(probe.devices):
        apis = [probe.devices[gpu_id][2]]
    else:
        apis = [api for _, _, api in probe.devices]
    return None if any(api >= VULKAN_REQUIRED for api in apis) else "old"


def vulkan_warning(
    problem: str, probe: VulkanProbe, gpu_id: Optional[int] = None
) -> Tuple[str, str]:
    """The question shown before the game starts, as (title, message), for vulkan_problem(probe, gpu_id).
    "missing" and "no_gpu": Vulkan is not found. "old": the version the game would get (the loader's when
    that is too old, else the GPU the game uses) and every GPU with its version."""
    need = "%d.%d" % VULKAN_REQUIRED
    if problem == "old":
        if probe.loader is not None and probe.loader < VULKAN_REQUIRED:
            have = probe.loader
        elif gpu_id is not None and 0 <= gpu_id < len(probe.devices):
            have = probe.devices[gpu_id][2]
        else:
            have = max(api for _, _, api in probe.devices)
        gpus = "".join(
            f"  • {name} — Vulkan {major}.{minor}\n"
            for name, _, (major, minor) in probe.devices
        )
        return "Vulkan Terlalu Lama", (
            f"⚠️ Game ini membutuhkan Vulkan {need}, tetapi PC ini baru mendukung Vulkan {have[0]}.{have[1]}.\n\n"
            + (f"Kartu grafis yang terdeteksi:\n{gpus}\n" if gpus else "")
            + "👉 Solusi: pasang driver terbaru dari situs resmi NVIDIA, AMD, atau Intel (bukan dari Windows Update), "
            "lalu restart PC.\n"
            f"Kalau driver sudah yang terbaru, kartu grafis ini belum mendukung Vulkan {need}, sehingga game "
            "tidak bisa berjalan di PC ini.\n\n"
            "Tetap coba jalankan game?"
        )
    return "Vulkan Tidak Ditemukan", (
        f"⚠️ Game ini membutuhkan Vulkan {need} untuk menampilkan grafis, tetapi Vulkan tidak ditemukan di PC ini.\n"
        "Biasanya karena driver kartu grafis belum terpasang, sudah lama, atau masih driver bawaan Windows.\n\n"
        "👉 Solusi:\n"
        "1. Pasang driver terbaru dari situs resmi NVIDIA, AMD, atau Intel (bukan dari Windows Update).\n"
        "2. Restart PC, lalu buka launcher lagi.\n\n"
        f"Kalau pesan ini masih muncul, kemungkinan kartu grafis PC ini belum mendukung Vulkan {need}, sehingga "
        "game tidak bisa berjalan.\n\n"
        "Tetap coba jalankan game?"
    )


def describe_vulkan(probe: VulkanProbe) -> str:
    """One line for the crash report: the loader and each GPU's Vulkan version against the requirement."""
    need = "%d.%d" % VULKAN_REQUIRED
    if not probe.loaded:
        return f"not found ({probe.error}); needs {need}"
    parts = ["loader " + ("%d.%d" % probe.loader if probe.loader else "unknown")]
    parts += [
        f"GPU {i} {major}.{minor}"
        for i, (_, _, (major, minor)) in enumerate(probe.devices)
    ] or ["no GPU" if probe.instance else "no instance"]
    if probe.error:
        parts.append(f"probe stopped: {probe.error}")
    return ", ".join(parts) + f"; needs {need}"


# Global initialization
VULKAN: VulkanProbe = probe_vulkan()
SYSTEM_GPUS: List[Tuple[int, str, bool]] = gpu_choices(VULKAN)


def enumerate_vulkan_gpus() -> List[Tuple[int, str, bool]]:
    return SYSTEM_GPUS


def resolve_spartan_gpu_id(selected_idx: int) -> Optional[str]:
    gid = game_gpu_id(selected_idx, SYSTEM_GPUS)
    return str(gid) if gid is not None else None
