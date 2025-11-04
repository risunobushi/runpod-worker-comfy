#!/usr/bin/env python3
"""
ComfyUI RunPod Test Script for QwenVTON Workflow
Tests virtual try-on with person and garment images via RunPod API
"""

import json
import sys
import time
import base64
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from urllib.parse import quote
from PIL import Image
from io import BytesIO


def load_workflow(workflow_path: str = "qwenVTON-test.json") -> Dict[str, Any]:
    """Load the ComfyUI workflow from JSON file."""
    with open(workflow_path, 'r') as f:
        return json.load(f)


def image_to_base64(image_path: str) -> str:
    """Convert image file to base64 string."""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def update_workflow(
    workflow: Dict[str, Any],
    person_image: str,
    garment_image: str
) -> Dict[str, Any]:
    """
    Update workflow with person and garment image paths.

    Args:
        workflow: The base workflow dictionary
        person_image: Path to person/model image
        garment_image: Path to garment image

    Returns:
        Updated workflow dictionary
    """
    workflow_copy = json.loads(json.dumps(workflow))  # Deep copy

    # Node 106 is Person Image
    if "106" in workflow_copy:
        workflow_copy["106"]["inputs"]["image"] = Path(person_image).name

    # Node 78 is Garment Image
    if "78" in workflow_copy:
        workflow_copy["78"]["inputs"]["image"] = Path(garment_image).name

    return workflow_copy


def prepare_api_request(
    workflow: Dict[str, Any],
    person_image_path: str,
    garment_image_path: str
) -> Dict[str, Any]:
    """
    Prepare the API request payload for RunPod.

    Args:
        workflow: ComfyUI workflow
        person_image_path: Path to person image
        garment_image_path: Path to garment image

    Returns:
        API request payload
    """
    # Read and encode images as base64
    person_image_b64 = image_to_base64(person_image_path)
    garment_image_b64 = image_to_base64(garment_image_path)

    # Get image filenames
    person_filename = Path(person_image_path).name
    garment_filename = Path(garment_image_path).name

    request_payload = {
        "input": {
            "workflow": workflow,
            "images": [
                {
                    "name": person_filename,
                    "image": person_image_b64
                },
                {
                    "name": garment_filename,
                    "image": garment_image_b64
                }
            ]
        }
    }

    return request_payload


def submit_job(
    endpoint_id: str,
    runpod_key: str,
    request_payload: Dict[str, Any],
    timeout: int = 600
) -> Optional[str]:
    """
    Submit a job to RunPod API and wait for completion.

    Args:
        endpoint_id: RunPod endpoint ID
        runpod_key: RunPod API key
        request_payload: Job payload
        timeout: Maximum wait time in seconds

    Returns:
        Job ID on success, None on failure
    """
    url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {runpod_key}"
    }

    print(f"[*] Submitting job to endpoint: {endpoint_id}")
    print(f"[*] URL: {url}")

    try:
        response = requests.post(url, json=request_payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "id" not in data:
            print(f"[!] Error: Invalid response - {data}")
            return None

        job_id = data["id"]
        print(f"[+] Job submitted successfully. Job ID: {job_id}")
        return job_id

    except requests.exceptions.RequestException as e:
        print(f"[!] Error submitting job: {e}")
        return None


def poll_job_status(
    endpoint_id: str,
    runpod_key: str,
    job_id: str,
    timeout: int = 600,
    poll_interval: int = 5
) -> Optional[Dict[str, Any]]:
    """
    Poll job status until completion or timeout.

    Args:
        endpoint_id: RunPod endpoint ID
        runpod_key: RunPod API key
        job_id: Job ID to poll
        timeout: Maximum wait time in seconds
        poll_interval: Interval between polls in seconds

    Returns:
        Job result on completion, None on failure/timeout
    """
    url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
    headers = {
        "Authorization": f"Bearer {runpod_key}"
    }

    start_time = time.time()

    print(f"[*] Polling job status (timeout: {timeout}s, interval: {poll_interval}s)")

    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            print(f"[*] Job status: {status}")

            if status == "COMPLETED":
                print("[+] Job completed successfully!")
                return data.get("output")

            elif status == "FAILED":
                print(f"[!] Job failed: {data.get('error')}")
                return None

            # Still processing
            time.sleep(poll_interval)

        except requests.exceptions.RequestException as e:
            print(f"[!] Error polling job: {e}")
            time.sleep(poll_interval)
            continue

    print(f"[!] Job timed out after {timeout} seconds")
    return None


def extract_output_data(job_output: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract the output image data from job result.

    ComfyUI returns output in various formats:
    {
        "images": [{"url": "..."} or "base64_string" or {"data": "base64_string"}]
    }
    or
    {
        "output_images": {...}  # RunPod wrapper format
    }

    Args:
        job_output: Job output dictionary

    Returns:
        Dictionary with 'type' and 'data' keys, or None if not found
    """
    if not job_output:
        return None

    # Handle direct URL response
    if isinstance(job_output, dict):
        if "url" in job_output:
            return {
                "type": "url",
                "data": job_output["url"]
            }

        # Check for output_images (RunPod wrapper format)
        if "output_images" in job_output:
            output_images = job_output["output_images"]
            if isinstance(output_images, dict) and len(output_images) > 0:
                # Get the first image from the dict
                first_key = next(iter(output_images))
                image_data = output_images[first_key]

                # Handle URL in images dict
                if isinstance(image_data, dict):
                    if "url" in image_data:
                        return {
                            "type": "url",
                            "data": image_data["url"]
                        }
                    # Check for "image" key (RunPod handler returns base64 under "image")
                    if "image" in image_data:
                        return {
                            "type": "base64",
                            "data": image_data["image"]
                        }
                    # Also check for "data" key as alternative
                    if "data" in image_data:
                        return {
                            "type": "base64",
                            "data": image_data["data"]
                        }

                # Handle direct base64 string in dict
                elif isinstance(image_data, str):
                    return {
                        "type": "base64",
                        "data": image_data
                    }

        # Check for images array
        if "images" in job_output and isinstance(job_output["images"], list):
            if len(job_output["images"]) > 0:
                image_data = job_output["images"][0]

                # Handle URL in images array
                if isinstance(image_data, dict):
                    if "url" in image_data:
                        return {
                            "type": "url",
                            "data": image_data["url"]
                        }
                    if "data" in image_data:
                        return {
                            "type": "base64",
                            "data": image_data["data"]
                        }

                # Handle direct base64 string in array
                elif isinstance(image_data, str):
                    return {
                        "type": "base64",
                        "data": image_data
                    }

    # Handle direct base64 string at root level
    if isinstance(job_output, str):
        return {
            "type": "base64",
            "data": job_output
        }

    # If structure is different, print for debugging
    output_str = json.dumps(job_output)
    if "http" in output_str or "data:image" in output_str:
        print("[*] Output structure (for reference):")
        print(json.dumps(job_output, indent=2)[:500])  # Truncate to avoid huge output

    return None


def decode_base64_image(base64_string: str, output_path: Path) -> bool:
    """
    Decode base64 image string and save as file.

    Args:
        base64_string: Base64 encoded image data
        output_path: Path where to save the image

    Returns:
        True if successful, False otherwise
    """
    try:
        # Handle data URL format
        if base64_string.startswith("data:image"):
            base64_string = base64_string.split(",")[1]

        # Decode base64
        image_data = base64.b64decode(base64_string)

        # Open with PIL to validate and get format
        image = Image.open(BytesIO(image_data))

        # Save image
        image.save(output_path)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"[+] Image saved: {output_path} ({size_mb:.2f}MB)")
        print(f"[+] Image format: {image.format}, Size: {image.size}")

        return True

    except Exception as e:
        print(f"[!] Error decoding/saving image: {e}")
        return False


def save_output_info(
    output_url: str,
    person_image: str,
    garment_image: str,
    output_file: str = "qwen_vton_result.json"
):
    """Save output information to JSON file."""
    result = {
        "status": "success",
        "output_url": output_url,
        "inputs": {
            "person_image": person_image,
            "garment_image": garment_image
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"[+] Result saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Test QwenVTON workflow via RunPod API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_qwen_vton.py \\
    --endpoint_id abc123xyz \\
    --runpod_key rk-xyz123... \\
    --person_image person.png \\
    --garment_image garment.png

  python test_qwen_vton.py \\
    --endpoint_id abc123xyz \\
    --runpod_key rk-xyz123... \\
    --person_image /path/to/person.jpg \\
    --garment_image /path/to/garment.jpg \\
    --workflow custom_workflow.json \\
    --timeout 900
        """
    )

    parser.add_argument(
        "--endpoint_id",
        required=True,
        help="RunPod endpoint ID"
    )
    parser.add_argument(
        "--runpod_key",
        required=True,
        help="RunPod API key"
    )
    parser.add_argument(
        "--person_image",
        required=True,
        help="Path to person/model image"
    )
    parser.add_argument(
        "--garment_image",
        required=True,
        help="Path to garment image"
    )
    parser.add_argument(
        "--workflow",
        default="qwenVTON-test.json",
        help="Path to ComfyUI workflow JSON (default: qwenVTON-test.json)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Job timeout in seconds (default: 600)"
    )
    parser.add_argument(
        "--poll_interval",
        type=int,
        default=5,
        help="Poll interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--output",
        default="qwen_vton_result.png",
        help="Output file path (image for base64 responses, JSON for URL responses) (default: qwen_vton_result.png)"
    )

    args = parser.parse_args()

    # Validate input files exist
    if not Path(args.person_image).exists():
        print(f"[!] Error: Person image not found: {args.person_image}")
        sys.exit(1)

    if not Path(args.garment_image).exists():
        print(f"[!] Error: Garment image not found: {args.garment_image}")
        sys.exit(1)

    if not Path(args.workflow).exists():
        print(f"[!] Error: Workflow not found: {args.workflow}")
        sys.exit(1)

    print("[*] QwenVTON RunPod Test Script")
    print(f"[*] Endpoint ID: {args.endpoint_id}")
    print(f"[*] Person Image: {args.person_image}")
    print(f"[*] Garment Image: {args.garment_image}")
    print(f"[*] Workflow: {args.workflow}")
    print()

    # Load and update workflow
    print("[*] Loading workflow...")
    workflow = load_workflow(args.workflow)
    workflow = update_workflow(workflow, args.person_image, args.garment_image)

    # Prepare API request
    print("[*] Preparing API request with base64-encoded images...")
    request_payload = prepare_api_request(
        workflow,
        args.person_image,
        args.garment_image
    )

    # Submit job
    job_id = submit_job(args.endpoint_id, args.runpod_key, request_payload, args.timeout)
    if not job_id:
        print("[!] Failed to submit job")
        sys.exit(1)

    print()

    # Poll for completion
    job_output = poll_job_status(
        args.endpoint_id,
        args.runpod_key,
        job_id,
        timeout=args.timeout,
        poll_interval=args.poll_interval
    )

    if not job_output:
        print("[!] Job did not complete successfully")
        sys.exit(1)

    print()

    # Extract output data (handles base64, URL, or dict formats)
    output_data = extract_output_data(job_output)
    if not output_data:
        print("[!] Could not extract output from job result")
        print("[*] Full job output:")
        print(json.dumps(job_output, indent=2))
        print()
        print("[*] The workflow COMPLETED SUCCESSFULLY but output_images is empty.")
        print("[*] This means:")
        print("    1. The ComfyUI workflow ran successfully")
        print("    2. The image WAS generated on the server (/comfyui/output/)")
        print("    3. But the RunPod handler didn't capture it in the response")
        print()
        print("[*] The issue is in the RunPod handler's image extraction logic.")
        print("[*] The handler needs to scan /comfyui/output/ and return any generated images.")
        print()
        print("[*] For now, you can:")
        print("    1. Check the RunPod worker logs for the actual generated filename")
        print("    2. Look for: 'Listing /comfyui/output contents AFTER workflow execution'")
        print("    3. The image exists there and can be extracted via RunPod's file API")
        sys.exit(1)

    print(f"[+] Output type: {output_data['type']}")

    # Handle based on output type
    if output_data["type"] == "base64":
        # Decode and save as image file
        output_path = Path(args.output)
        if not decode_base64_image(output_data["data"], output_path):
            print("[!] Failed to decode and save image")
            sys.exit(1)
        print("[+] Test completed successfully!")
        print(f"[+] Image saved to: {output_path}")

    elif output_data["type"] == "url":
        # Save URL to file for reference
        output_url = output_data["data"]
        print(f"[+] Output URL: {output_url}")
        print()
        save_output_info(output_url, args.person_image, args.garment_image, args.output)
        print("[+] Test completed successfully!")
        print(f"[+] Result saved to: {args.output}")
        print(f"[+] Output Image URL: {output_url}")


if __name__ == "__main__":
    main()
