#!/usr/bin/env python3
"""
Batch QwenVTON Test Script
Processes all combinations of person and garment images from given directories
"""

import json
import sys
import time
import base64
import argparse
import subprocess
from pathlib import Path
from typing import List, Tuple
from datetime import datetime


def get_image_files(directory: str) -> List[Path]:
    """Get all image files from a directory."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    directory_path = Path(directory)

    if not directory_path.exists():
        print(f"[!] Error: Directory not found: {directory}")
        sys.exit(1)

    images = [f for f in directory_path.iterdir()
              if f.is_file() and f.suffix.lower() in image_extensions]

    if not images:
        print(f"[!] Error: No image files found in {directory}")
        sys.exit(1)

    return sorted(images)


def create_output_dir(base_dir: str = "batch_results") -> str:
    """Create output directory with timestamp."""
    output_dir = Path(base_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] Output directory: {output_dir}")
    return str(output_dir)


def run_single_job(
    person_image: Path,
    garment_image: Path,
    endpoint_id: str,
    runpod_key: str,
    workflow: str,
    output_dir: str,
    timeout: int = 600,
    poll_interval: int = 5
) -> Tuple[bool, str]:
    """
    Run a single test_qwen_vton.py job for a person/garment combination.

    Returns:
        Tuple of (success: bool, output_file: str)
    """
    # Generate output filename from input filenames
    person_name = person_image.stem
    garment_name = garment_image.stem
    output_file = f"{output_dir}/{person_name}__x__{garment_name}.png"

    # Build command
    cmd = [
        "python", "test_qwen_vton.py",
        "--workflow", workflow,
        "--endpoint_id", endpoint_id,
        "--runpod_key", runpod_key,
        "--person_image", str(person_image),
        "--garment_image", str(garment_image),
        "--output", output_file,
        "--timeout", str(timeout),
        "--poll_interval", str(poll_interval)
    ]

    print(f"[*] Processing: {person_name} × {garment_name}")
    print(f"    Person: {person_image.name}")
    print(f"    Garment: {garment_image.name}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 30  # Give extra time for process overhead
        )

        if result.returncode == 0:
            print(f"[+] Success: {output_file}")
            return True, output_file
        else:
            print(f"[!] Failed with exit code {result.returncode}")
            if result.stderr:
                print(f"    Error: {result.stderr[:200]}")
            return False, output_file

    except subprocess.TimeoutExpired:
        print(f"[!] Process timeout exceeded")
        return False, output_file
    except Exception as e:
        print(f"[!] Error running job: {e}")
        return False, output_file


def main():
    parser = argparse.ArgumentParser(
        description="Batch process all combinations of person and garment images"
    )
    parser.add_argument(
        "--people_dir",
        required=True,
        help="Directory containing person images"
    )
    parser.add_argument(
        "--garments_dir",
        required=True,
        help="Directory containing garment images"
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
        "--workflow",
        default="qwenVTON-test.json",
        help="Workflow file to use (default: qwenVTON-test.json)"
    )
    parser.add_argument(
        "--output_dir",
        default="batch_results",
        help="Base output directory (default: batch_results)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout per job in seconds (default: 600)"
    )
    parser.add_argument(
        "--poll_interval",
        type=int,
        default=5,
        help="Poll interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2,
        help="Delay between jobs in seconds (default: 2)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of combinations to process (default: all)"
    )

    args = parser.parse_args()

    # Get image files
    print("[*] Scanning directories...")
    people_images = get_image_files(args.people_dir)
    garments_images = get_image_files(args.garments_dir)

    print(f"[*] Found {len(people_images)} person image(s)")
    print(f"[*] Found {len(garments_images)} garment image(s)")
    print(f"[*] Total combinations: {len(people_images) * len(garments_images)}")
    print()

    # Create output directory
    output_dir = create_output_dir(args.output_dir)

    # Process combinations
    total_jobs = len(people_images) * len(garments_images)
    if args.limit:
        total_jobs = min(total_jobs, args.limit)

    completed = 0
    successful = 0
    failed = 0
    results = []

    start_time = time.time()

    for idx, (person_image, garment_image) in enumerate(
        [(p, g) for p in people_images for g in garments_images]
    ):
        if args.limit and idx >= args.limit:
            print(f"\n[*] Reached limit of {args.limit} combinations")
            break

        job_num = idx + 1
        print(f"\n[*] Job {job_num}/{total_jobs}")
        print(f"[*] Time elapsed: {time.time() - start_time:.1f}s")

        success, output_file = run_single_job(
            person_image,
            garment_image,
            args.endpoint_id,
            args.runpod_key,
            args.workflow,
            output_dir,
            args.timeout,
            args.poll_interval
        )

        completed += 1
        if success:
            successful += 1
        else:
            failed += 1

        results.append({
            "person": person_image.name,
            "garment": garment_image.name,
            "success": success,
            "output": output_file
        })

        # Delay between jobs
        if idx < total_jobs - 1:
            print(f"[*] Waiting {args.delay}s before next job...")
            time.sleep(args.delay)

    # Print summary
    elapsed_time = time.time() - start_time
    print("\n" + "=" * 80)
    print("BATCH PROCESSING SUMMARY")
    print("=" * 80)
    print(f"Total jobs:     {completed}")
    print(f"Successful:     {successful}")
    print(f"Failed:         {failed}")
    print(f"Time elapsed:   {elapsed_time:.1f}s")
    print(f"Output dir:     {output_dir}")
    print("=" * 80)

    # Save results to JSON
    results_file = f"{output_dir}/batch_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": completed,
                "successful": successful,
                "failed": failed,
                "elapsed_time_seconds": elapsed_time
            },
            "results": results
        }, f, indent=2)

    print(f"[+] Results saved to: {results_file}")

    # Exit with error if any jobs failed
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
