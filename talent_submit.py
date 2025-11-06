#!/usr/bin/env python3
"""
Talent Zero Workflow Submitter

Submit the talent-0-0-1 ComfyUI workflow to a RunPod serverless endpoint,
populate it with user images and parameters, and retrieve the output image.

The script handles:
- Loading the workflow template
- Injecting user images (base64 encoded)
- Populating workflow parameters
- Submitting to RunPod
- Polling for completion
- Extracting and saving the output image from base64
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import requests


class TalentWorkflowSubmitter:
    """Submit and monitor talent_zero workflow jobs on RunPod."""

    def __init__(
        self,
        endpoint_id: str,
        api_key: str,
        workflow_template_path: str,
        base_url: str = "https://api.runpod.ai/v2",
        timeout: int = 600,
        poll_interval: float = 5.0,
    ):
        """
        Initialize the submitter.

        Args:
            endpoint_id: RunPod endpoint ID
            api_key: RunPod API key
            workflow_template_path: Path to talent workflow JSON file
            base_url: RunPod API base URL
            timeout: Max time to wait for job completion (seconds)
            poll_interval: Time between status checks (seconds)
        """
        self.endpoint_id = endpoint_id
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

        # Load workflow template
        with open(workflow_template_path, "r") as f:
            self.workflow_template = json.load(f)

    def _encode_image_to_base64(self, image_path: str) -> str:
        """Encode image file to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _decode_base64_image(self, base64_str: str, output_path: str) -> None:
        """Decode base64 image string and save to file."""
        image_bytes = base64.b64decode(base64_str)
        with open(output_path, "wb") as f:
            f.write(image_bytes)

    def prepare_workflow(
        self,
        image_path: str,
        photo_type: str = "Ultra-realistic studio fashion photo",
        shot_type: str = "full-body shot",
        gender: str = "unspecified",
        build: str = "unspecified",
        height: str = "unspecified",
        skin_tone: str = "unspecified",
        hair_length: str = "unspecified",
        hair_color: str = "unspecified",
        expression: str = "unspecified",
        clothing_upper: str = "",
        clothing_lower: str = "",
        footwear: str = "",
        extra_guidance: str = "",
    ) -> Dict[str, Any]:
        """
        Prepare workflow by injecting image and parameters.

        Args:
            image_path: Path to input image file
            photo_type: Photo type for talent_zero_combine node
            shot_type: Shot type for talent_zero_combine node
            gender: Gender for talent_zero_combine node
            build: Build for talent_zero_combine node
            height: Height for talent_zero_combine node
            skin_tone: Skin tone for talent_zero_combine node
            hair_length: Hair length for talent_zero_combine node
            hair_color: Hair color for talent_zero_combine node
            expression: Expression for talent_zero_combine node
            clothing_upper: Clothing upper for talent_zero_combine node
            clothing_lower: Clothing lower for talent_zero_combine node
            footwear: Footwear for talent_zero_combine node
            extra_guidance: Extra guidance for talent_zero_combine node

        Returns:
            Populated workflow dictionary
        """
        workflow = json.loads(json.dumps(self.workflow_template))

        # Get the filename for LoadImage node (node 11)
        image_filename = Path(image_path).name

        # Update LoadImage node (node "11") with the image filename
        if "11" in workflow:
            workflow["11"]["inputs"]["image"] = image_filename

        # Update talent_zero_combine node (node "20") with parameters
        if "20" in workflow:
            workflow["20"]["inputs"].update({
                "photo_type": photo_type,
                "shot_type": shot_type,
                "gender": gender,
                "build": build,
                "height": height,
                "skin_tone": skin_tone,
                "hair_length": hair_length,
                "hair_color": hair_color,
                "expression": expression,
                "clothing_upper": clothing_upper,
                "clothing_lower": clothing_lower,
                "footwear": footwear,
            })
            if extra_guidance:
                workflow["20"]["inputs"]["extra_guidance"] = extra_guidance

        return workflow

    def submit_job(
        self,
        workflow: Dict[str, Any],
        image_path: str,
    ) -> str:
        """
        Submit workflow job to RunPod.

        Args:
            workflow: ComfyUI workflow dictionary
            image_path: Path to input image (for upload)

        Returns:
            Job ID
        """
        # Encode image to base64
        image_base64 = self._encode_image_to_base64(image_path)
        image_filename = Path(image_path).name

        payload = {
            "input": {
                "workflow": workflow,
                "images": [
                    {
                        "name": image_filename,
                        "image": image_base64,
                    }
                ],
            }
        }

        url = f"{self.base_url}/{self.endpoint_id}/run"

        print(f"\n📤 Submitting job to RunPod...")
        print(f"   Endpoint: {self.endpoint_id}")
        print(f"   Image: {image_filename}")
        print(f"   Workflow nodes: {len(workflow)}")

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        job_id = result.get("id")

        if not job_id:
            raise ValueError(f"No job ID in response: {result}")

        print(f"✅ Job submitted with ID: {job_id}")
        return job_id

    def poll_job(self, job_id: str) -> Dict[str, Any]:
        """
        Poll for job completion and retrieve results.

        Args:
            job_id: Job ID returned from submit_job

        Returns:
            Job output dictionary
        """
        url = f"{self.base_url}/{self.endpoint_id}/status/{job_id}"
        start_time = time.time()

        print(f"\n⏳ Polling for job completion...")

        while True:
            elapsed = time.time() - start_time

            if elapsed > self.timeout:
                raise TimeoutError(
                    f"Job did not complete within {self.timeout} seconds"
                )

            response = self.session.get(url)
            response.raise_for_status()

            result = response.json()
            status = result.get("status")

            print(f"   [{elapsed:.1f}s] Status: {status}")

            if status == "COMPLETED":
                print(f"✅ Job completed successfully")
                return result.get("output", {})

            if status == "FAILED":
                error = result.get("error", "Unknown error")
                print(f"❌ Job failed: {error}")
                raise RuntimeError(f"Job failed: {error}")

            time.sleep(self.poll_interval)

    def extract_image_from_output(self, output: Dict[str, Any]) -> Optional[str]:
        """
        Extract base64 image data from job output.

        RunPod/ComfyUI returns images in the output_images dict.
        Structure: output_images[filename] = {"image": base64_string}

        Args:
            output: Job output dictionary

        Returns:
            Base64 image string, or None if not found
        """
        # Try output_images first (standard ComfyUI format)
        if "output_images" in output:
            for filename, image_data in output["output_images"].items():
                if isinstance(image_data, dict) and "image" in image_data:
                    return image_data["image"]
                elif isinstance(image_data, str):
                    # Direct base64 string
                    return image_data

        # Fallback: check for direct image data in output
        for key, value in output.items():
            if isinstance(value, dict) and "image" in value:
                return value["image"]
            elif isinstance(value, str) and len(value) > 100:
                # Might be base64
                return value

        return None

    def save_output_image(self, output: Dict[str, Any], output_path: str) -> bool:
        """
        Extract image from output and save to file.

        Args:
            output: Job output dictionary
            output_path: Path where to save the image

        Returns:
            True if successful, False otherwise
        """
        image_base64 = self.extract_image_from_output(output)

        if not image_base64:
            print("❌ No image found in job output")
            return False

        try:
            self._decode_base64_image(image_base64, output_path)
            print(f"💾 Image saved to: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to save image: {e}")
            return False

    def run(
        self,
        image_path: str,
        output_path: str,
        **kwargs,
    ) -> bool:
        """
        Run complete workflow: prepare, submit, poll, and save output.

        Args:
            image_path: Path to input image
            output_path: Path where to save output image
            **kwargs: Additional parameters for prepare_workflow

        Returns:
            True if successful, False otherwise
        """
        if not Path(image_path).exists():
            print(f"❌ Input image not found: {image_path}")
            return False

        # Prepare workflow
        workflow = self.prepare_workflow(image_path, **kwargs)
        print(f"📋 Workflow prepared")

        # Submit job
        job_id = self.submit_job(workflow, image_path)

        # Poll for completion
        output = self.poll_job(job_id)

        # Save output image
        return self.save_output_image(output, output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Submit talent_zero workflow to RunPod and save output image",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  # Basic usage with defaults
  python talent_submit.py --endpoint-id abc123xyz --apikey-runpod your-key \\
    --image input.jpg --output result.jpg

  # With custom parameters
  python talent_submit.py --endpoint-id abc123xyz --apikey-runpod your-key \\
    --image person.jpg --output result.jpg \\
    --photo-type "Ultra-realistic runway fashion photo" \\
    --shot-type "full-body shot" \\
    --gender "female" \\
    --build "athletic" \\
    --footwear "heels"

  # Using environment variables
  export RUNPOD_ENDPOINT_ID=abc123xyz
  export RUNPOD_API_KEY=your-key
  python talent_submit.py --image input.jpg --output result.jpg

  # Custom timeout and polling
  python talent_submit.py --endpoint-id abc123xyz --apikey-runpod your-key \\
    --image input.jpg --output result.jpg \\
    --timeout 1200 --poll-interval 3
        """,
    )

    # Required arguments
    parser.add_argument(
        "--endpoint-id",
        required=False,
        help="RunPod endpoint ID (or set RUNPOD_ENDPOINT_ID env var)",
    )
    parser.add_argument(
        "--apikey-runpod",
        required=False,
        help="RunPod API key (or set RUNPOD_API_KEY env var)",
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to input image file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path where to save output image",
    )

    # Workflow template
    parser.add_argument(
        "--workflow",
        default="talent-0-0-1.json",
        help="Path to workflow template JSON (default: talent-0-0-1.json)",
    )

    # Workflow parameters
    parser.add_argument(
        "--photo-type",
        default="Ultra-realistic studio fashion photo",
        help="Photo type",
    )
    parser.add_argument(
        "--shot-type",
        default="full-body shot",
        help="Shot type",
    )
    parser.add_argument(
        "--gender",
        default="unspecified",
        help="Gender",
    )
    parser.add_argument(
        "--build",
        default="unspecified",
        help="Build type",
    )
    parser.add_argument(
        "--height",
        default="unspecified",
        help="Height",
    )
    parser.add_argument(
        "--skin-tone",
        default="unspecified",
        help="Skin tone",
    )
    parser.add_argument(
        "--hair-length",
        default="unspecified",
        help="Hair length",
    )
    parser.add_argument(
        "--hair-color",
        default="unspecified",
        help="Hair color",
    )
    parser.add_argument(
        "--expression",
        default="unspecified",
        help="Expression",
    )
    parser.add_argument(
        "--clothing-upper",
        default="",
        help="Clothing upper description",
    )
    parser.add_argument(
        "--clothing-lower",
        default="",
        help="Clothing lower description",
    )
    parser.add_argument(
        "--footwear",
        default="",
        help="Footwear description",
    )
    parser.add_argument(
        "--extra-guidance",
        default="",
        help="Extra guidance text",
    )

    # RunPod configuration
    parser.add_argument(
        "--base-url",
        default="https://api.runpod.ai/v2",
        help="RunPod API base URL",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Max time to wait for job (seconds, default: 600)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Time between status checks (seconds, default: 5.0)",
    )

    args = parser.parse_args()

    # Get credentials from args or environment
    endpoint_id = args.endpoint_id or os.environ.get("RUNPOD_ENDPOINT_ID")
    api_key = args.apikey_runpod or os.environ.get("RUNPOD_API_KEY")

    if not endpoint_id:
        print("❌ Error: --endpoint-id or RUNPOD_ENDPOINT_ID env var required")
        sys.exit(1)

    if not api_key:
        print("❌ Error: --apikey-runpod or RUNPOD_API_KEY env var required")
        sys.exit(1)

    if not Path(args.workflow).exists():
        print(f"❌ Error: Workflow template not found: {args.workflow}")
        sys.exit(1)

    if not Path(args.image).exists():
        print(f"❌ Error: Input image not found: {args.image}")
        sys.exit(1)

    # Run the workflow
    try:
        submitter = TalentWorkflowSubmitter(
            endpoint_id=endpoint_id,
            api_key=api_key,
            workflow_template_path=args.workflow,
            base_url=args.base_url,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
        )

        success = submitter.run(
            image_path=args.image,
            output_path=args.output,
            photo_type=args.photo_type,
            shot_type=args.shot_type,
            gender=args.gender,
            build=args.build,
            height=args.height,
            skin_tone=args.skin_tone,
            hair_length=args.hair_length,
            hair_color=args.hair_color,
            expression=args.expression,
            clothing_upper=args.clothing_upper,
            clothing_lower=args.clothing_lower,
            footwear=args.footwear,
            extra_guidance=args.extra_guidance,
        )

        if success:
            print("\n✨ Workflow completed and image saved successfully!")
            sys.exit(0)
        else:
            print("\n❌ Failed to save output image")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
