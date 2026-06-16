"""Upload Dockerfile + README to the Hugging Face Space (no git credentials needed)."""

import os
import sys

from huggingface_hub import HfApi

SPACE_ID = "Gayaththri/PROSE-MEET"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPACE_FILES = os.path.join(REPO_ROOT, "deploy", "huggingface", "space-repo")


def main() -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        print("Missing HF_TOKEN.")
        print("1. Create a Write token: https://huggingface.co/settings/tokens")
        print("2. Run in PowerShell:")
        print('   $env:HF_TOKEN="hf_..."')
        print("   python scripts/push_hf_space.py")
        return 1

    api = HfApi(token=token)
    uploads = [
        ("Dockerfile", os.path.join(SPACE_FILES, "Dockerfile")),
        ("README.md", os.path.join(SPACE_FILES, "README.md")),
    ]

    for path_in_repo, local_path in uploads:
        if not os.path.isfile(local_path):
            print(f"Missing file: {local_path}")
            return 1
        print(f"Uploading {path_in_repo} ...")
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=path_in_repo,
            repo_id=SPACE_ID,
            repo_type="space",
            commit_message="Deploy PROSE-MEET full stack (UI + FastAPI + Whisper)",
        )

    print()
    print("Done. Hugging Face will start building automatically.")
    print("Open: https://huggingface.co/spaces/Gayaththri/PROSE-MEET")
    print("First build: 10-20 minutes. Status must show Running before testing uploads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
