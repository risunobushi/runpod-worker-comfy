#!/usr/bin/env python3
"""
Download QwenVTON required models for ComfyUI
Downloads Qwen 2.5 VL, qwenVTON model, and VAE
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional
import requests
from tqdm import tqdm


# Model URLs (update these with actual model URLs)
MODELS = {
    "clip": {
        "name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "url": "https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct/resolve/main/model.safetensors",  # Example URL
        "directory": "models/clip",
        "description": "Qwen 2.5 VL 7B FP8 Scaled CLIP Model"
    },
    "unet": {
        "name": "qwenVTON-single.safetensors",
        "url": "https://huggingface.co/levihsu/qwenVTON/resolve/main/qwenVTON-single.safetensors",  # Example URL
        "directory": "models/unet",
        "description": "QwenVTON UNET Model"
    },
    "vae": {
        "name": "qwen_image_vae.safetensors",
        "url": "https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct/resolve/main/vae/model.safetensors",  # Example URL
        "directory": "models/vae",
        "description": "Qwen Image VAE Model"
    }
}


def download_file(url: str, destination: Path, timeout: int = 300) -> bool:
    """
    Download a file from URL with progress bar.

    Args:
        url: URL to download from
        destination: Path where to save the file
        timeout: Download timeout in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"[*] Downloading from: {url}")

        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        with open(destination, 'wb') as f:
            if total_size > 0:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=destination.name) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

        print(f"[+] Downloaded: {destination.name}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"[!] Error downloading {url}: {e}")
        return False


def check_model_exists(path: Path) -> bool:
    """Check if model file exists and has reasonable size."""
    if not path.exists():
        return False

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb < 10:  # Models should be at least 10MB
        print(f"[!] Model file is suspiciously small: {size_mb:.2f}MB")
        return False

    return True


def setup_models(base_dir: Path = Path("/comfyui"), force: bool = False, huggingface_token: Optional[str] = None) -> bool:
    """
    Download and setup all required models.

    Args:
        base_dir: ComfyUI base directory
        force: Force re-download even if files exist
        huggingface_token: HuggingFace token for authenticated downloads

    Returns:
        True if all models are ready, False otherwise
    """
    print("[*] QwenVTON Model Setup")
    print(f"[*] Base directory: {base_dir}")
    print()

    all_ready = True

    for model_key, model_info in MODELS.items():
        print(f"[*] {model_info['description']}")

        # Prepare directory
        model_dir = base_dir / model_info['directory']
        model_dir.mkdir(parents=True, exist_ok=True)

        # Check if file exists
        model_path = model_dir / model_info['name']

        if model_path.exists() and not force:
            if check_model_exists(model_path):
                size_mb = model_path.stat().st_size / (1024 * 1024)
                print(f"[+] Already exists: {model_path.name} ({size_mb:.2f}MB)")
                print()
                continue
            else:
                print(f"[!] Existing file is incomplete, re-downloading...")
                model_path.unlink()

        # Download model
        url = model_info['url']

        # Add token to URL if provided and it's HuggingFace
        if huggingface_token and "huggingface.co" in url:
            url = url + f"?token={huggingface_token}"

        if not download_file(url, model_path):
            print(f"[!] Failed to download: {model_info['name']}")
            all_ready = False
        else:
            if check_model_exists(model_path):
                size_mb = model_path.stat().st_size / (1024 * 1024)
                print(f"[+] Model ready: {model_path.name} ({size_mb:.2f}MB)")
            else:
                print(f"[!] Downloaded file appears corrupted: {model_path.name}")
                all_ready = False

        print()

    return all_ready


def generate_manifest(base_dir: Path = Path("/comfyui"), output_file: str = "qwen_models_manifest.json"):
    """Generate a manifest file listing all models."""
    manifest = {
        "qwen_vton_models": {
            "models": {}
        }
    }

    for model_key, model_info in MODELS.items():
        model_dir = base_dir / model_info['directory']
        model_path = model_dir / model_info['name']

        manifest["qwen_vton_models"]["models"][model_key] = {
            "name": model_info['name'],
            "directory": model_info['directory'],
            "description": model_info['description'],
            "exists": model_path.exists(),
            "size_mb": model_path.stat().st_size / (1024 * 1024) if model_path.exists() else 0
        }

    with open(output_file, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"[+] Manifest saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Download QwenVTON models for ComfyUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download to default ComfyUI location
  python download_qwen_models.py

  # Download to custom location
  python download_qwen_models.py --base_dir /path/to/comfyui

  # Force re-download even if files exist
  python download_qwen_models.py --force

  # Use HuggingFace token for authenticated access
  python download_qwen_models.py --hf_token YOUR_TOKEN

  # Download and generate manifest
  python download_qwen_models.py --manifest
        """
    )

    parser.add_argument(
        "--base_dir",
        type=Path,
        default=Path("/comfyui"),
        help="ComfyUI base directory (default: /comfyui)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if files exist"
    )
    parser.add_argument(
        "--hf_token",
        help="HuggingFace token for authenticated downloads"
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Generate manifest file after download"
    )

    args = parser.parse_args()

    # Validate base directory
    if not args.base_dir.exists():
        print(f"[!] Error: Base directory does not exist: {args.base_dir}")
        print(f"[*] Creating directory...")
        args.base_dir.mkdir(parents=True, exist_ok=True)

    # Download models
    success = setup_models(args.base_dir, force=args.force, huggingface_token=args.hf_token)

    if args.manifest:
        generate_manifest(args.base_dir)

    if success:
        print("[+] All models ready!")
        sys.exit(0)
    else:
        print("[!] Some models failed to download")
        sys.exit(1)


if __name__ == "__main__":
    main()
