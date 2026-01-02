#!/usr/bin/env python3
"""
ASU Client - Two-step workflow (prepare + build)

Usage:
    # Use two-step workflow (default):
    python uclient.py config.json

    # Use legacy single-step workflow:
    python uclient.py config.json --legacy

    # Use prepare-only mode to see changes without building:
    python uclient.py config.json --prepare-only

Config JSON format:
{
    "url": "http://localhost:8000",
    "prepare_url": "http://localhost:8001",  // Optional, for two-step mode
    "version": "23.05.5",
    "target": "ath79/generic", 
    "profile": "tplink_tl-wdr4300-v1",
    "packages": ["luci", "vim"],
    "defaults": "...",  // Optional
    "diff_packages": true  // Optional
}
"""

import json
import sys
from pathlib import Path
from time import sleep
from typing import Optional

import requests


def do_prepare(prepare_url: str, data: dict) -> dict:
    """
    Step 1: Call prepare endpoint to resolve packages and get changes.
    
    Returns the prepare response with resolved packages and changes.
    """
    request = {
        "version": data["version"],
        "target": data["target"],
        "profile": data["profile"],
    }
    
    if "packages" in data:
        request["packages"] = data["packages"]
    
    if "packages_versions" in data:
        request["packages"] = list(data["packages_versions"].keys())
    
    if "from_version" in data:
        request["from_version"] = data["from_version"]
    
    print(f"📝 Preparing build request...")
    response = requests.post(f"{prepare_url}/api/v1/prepare", json=request)
    
    if response.status_code != 200:
        print(f"❌ Prepare failed: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    return response.json()


def show_prepare_results(prepare_data: dict):
    """Display prepare results to user"""
    print("\n✅ Preparation complete!")
    print(f"Request hash: {prepare_data['request_hash']}")
    
    if prepare_data["changes"]:
        print(f"\n📦 Package changes ({len(prepare_data['changes'])}):")
        for change in prepare_data["changes"]:
            if change["type"] == "migration":
                print(f"  🔄 Migration: {change['from_package']} → {change['to_package']}")
                print(f"     Reason: {change['reason']}")
            elif change["type"] == "addition":
                print(f"  ➕ Addition: {change['package']}")
                print(f"     Reason: {change['reason']}")
            elif change["type"] == "removal":
                print(f"  ➖ Removal: {change['package']}")
                print(f"     Reason: {change['reason']}")
    else:
        print("\n✨ No package changes needed")
    
    print(f"\nFinal packages ({len(prepare_data['resolved_packages'])}):")
    for pkg in sorted(prepare_data['resolved_packages']):
        print(f"  - {pkg}")


def do_build(build_url: str, prepare_data: dict, original_data: dict) -> dict:
    """
    Step 2: Call build endpoint with prepared request.
    
    Polls until build completes or fails.
    """
    # Build request combines prepared request with build-specific fields
    request = {
        **prepare_data["prepared_request"],
        "diff_packages": original_data.get("diff_packages", False),
    }
    
    # Add build-specific fields if present
    if "defaults" in original_data:
        request["defaults"] = original_data["defaults"]
    
    if "rootfs_size_mb" in original_data:
        request["rootfs_size_mb"] = original_data["rootfs_size_mb"]
    
    if "repositories" in original_data:
        request["repositories"] = original_data["repositories"]
    
    if "repository_keys" in original_data:
        request["repository_keys"] = original_data["repository_keys"]
    
    print(f"\n🔨 Starting build...")
    response = requests.post(f"{build_url}/api/v1/build", json=request)
    
    # Poll until completion
    while response.status_code == 202:
        response_json = response.json()
        status = response_json.get("imagebuilder_status", "unknown")
        
        if "queue_position" in response_json:
            print(f"⏳ Queued at position {response_json['queue_position']}")
        else:
            print(f"⚙️  Building: {status}")
        
        sleep(1)
        
        # Poll using request hash
        request_hash = response_json["request_hash"]
        response = requests.get(f"{build_url}/api/v1/build/{request_hash}")
    
    return response.json()


def do_legacy_build(build_url: str, data: dict) -> dict:
    """
    Legacy single-step workflow (direct to /build without prepare).
    
    This is the old behavior for backwards compatibility.
    """
    request = {
        "target": data["target"],
        "version": data["version"],
        "profile": data["profile"],
    }
    
    if "packages" in data:
        request["packages"] = data["packages"]

    if "packages_versions" in data:
        request["packages"] = list(data["packages_versions"].keys())

    if "defaults" in data:
        request["defaults"] = data["defaults"]
    
    if "diff_packages" in data:
        request["diff_packages"] = data["diff_packages"]

    print(f"🔨 Building (legacy mode)...")
    response = requests.post(f"{build_url}/api/v1/build", json=request)
    
    # Poll until completion
    while response.status_code == 202:
        response_json = response.json()
        print(f"⚙️  Building: {response_json.get('imagebuilder_status', 'unknown')}")
        sleep(1)
        request_hash = response_json["request_hash"]
        response = requests.get(f"{build_url}/api/v1/build/{request_hash}")
    
    return response.json()


def show_build_results(result: dict):
    """Display build results"""
    print("\n" + "="*60)
    
    if "detail" in result:
        # Error occurred
        print(f"❌ Build failed: {result['detail']}")
        if "stdout" in result:
            print("\nSTDOUT:")
            print(result["stdout"])
        if "stderr" in result:
            print("\nSTDERR:")
            print(result["stderr"])
        sys.exit(1)
    else:
        # Success
        print("✅ Build completed successfully!")
        print(f"\nVersion: {result.get('version_number', 'unknown')}")
        print(f"Request hash: {result['request_hash']}")
        
        if "images" in result:
            print(f"\n📦 Images ({len(result['images'])}):")
            for image in result["images"]:
                print(f"  - {image['name']}")
                print(f"    Type: {image.get('type', 'unknown')}")
                print(f"    SHA256: {image.get('sha256', 'unknown')}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python uclient.py <config.json> [--legacy] [--prepare-only]")
        sys.exit(1)
    
    config_path = Path(sys.argv[1])
    legacy_mode = "--legacy" in sys.argv
    prepare_only = "--prepare-only" in sys.argv
    
    data = json.loads(config_path.read_text())
    
    build_url = data["url"]
    prepare_url = data.get("prepare_url", "http://localhost:8001")
    
    if legacy_mode:
        # Old single-step workflow
        print("🔧 Using legacy single-step workflow")
        result = do_legacy_build(build_url, data)
        show_build_results(result)
    else:
        # New two-step workflow
        print("🚀 Using two-step workflow (prepare + build)")
        
        # Step 1: Prepare
        prepare_data = do_prepare(prepare_url, data)
        show_prepare_results(prepare_data)
        
        if prepare_only:
            print("\n✋ Stopping after prepare (--prepare-only mode)")
            print("\nTo build with these changes, remove --prepare-only flag")
            sys.exit(0)
        
        # Ask user to confirm if there are changes
        if prepare_data["changes"]:
            response = input("\n❓ Proceed with build? [Y/n] ")
            if response.lower() in ["n", "no"]:
                print("❌ Build cancelled by user")
                sys.exit(0)
        
        # Step 2: Build
        result = do_build(build_url, prepare_data, data)
        show_build_results(result)


if __name__ == "__main__":
    main()
