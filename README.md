# VLC Frame Enhancer

VLC snapshot -> crop -> enhance -> compare. This project adds a VLC Lua
extension that triggers a snapshot, launches a Python UI, sends the cropped
frame to Gemini on Vertex AI, and shows a side-by-side result.

This repo includes the portable scripts `banana_snipper_public.py` and
`nano_trigger_public.lua`.

## Requirements
- Windows (uses Win32 APIs and VLC Windows paths)
- VLC
- Python 3.10+
- Google Cloud project with Vertex AI enabled

Python dependencies:
- `google-genai`
- `opencv-python`
- `numpy`
- `pillow`

## Setup (portable/public)
1) Install dependencies:
```bash
pip install google-genai opencv-python numpy pillow
```

2) Authenticate with Google Cloud (Application Default Credentials):
```bash
gcloud auth application-default login
```
Make sure the Vertex AI API is enabled for your project.

3) Place the VLC Lua extension at:
`C:\Users\[User]\AppData\Roaming\vlc\lua\extensions`

Copy `nano_trigger_public.lua` into that folder and restart VLC.

4) Edit `nano_trigger_public.lua`:
- `target_dir` should match VLC snapshot directory
  (VLC: Tools -> Preferences -> Video -> Directory).
- `python_exe` should point to your Python executable (or keep `python` if it is
  on PATH).
- `script_path` should point to `banana_snipper_public.py`.

5) Set optional environment variables for `banana_snipper_public.py`:
- `NANO_BANANA_PROJECT` (required for Vertex AI)
- `NANO_BANANA_LOCATION` (default: `global`)
- `NANO_BANANA_MODEL` (default: `gemini-3-pro-image-preview`)
- `NANO_BANANA_SNAPSHOT_DIR` (default: `%USERPROFILE%\Pictures\VLC Snapshots`)

6) In VLC, open the extension:
View -> Extensions -> Nano Banana Snapper

## Notes
- This tool sends image data to Google Vertex AI for processing.
- There is no local API server; everything runs in the VLC extension + Python.

## Known issues
- The first run after opening VLC may fail to detect the snapshot and will
  print "Waiting for VLC... (1/10)" up to "(10/10)". Retrying once usually works.

## License
MIT. See `LICENSE`.
