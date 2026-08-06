"""Render the current JB100 swarm blend as a small NTSC-size preview."""
import glob
import os
import shutil
import subprocess

import bpy


ROOT = os.getcwd()
OUT = os.path.join(ROOT, "scene_versions", "jb100_hyberspace_swarm_v1.0.16", "ntsc_preview")
FRAMES = os.path.join(OUT, "frames")
MP4 = os.path.join(OUT, "jb100_hyberspace_swarm_v1.0.16_ntsc_preview.mp4")

os.makedirs(FRAMES, exist_ok=True)

scene = bpy.context.scene
scene.render.resolution_x = 720
scene.render.resolution_y = 480
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 240
scene.render.filepath = os.path.join(FRAMES, "frame_")

# Render a 720x480 NTSC-raster preview while keeping the widescreen composition
# intent in the encoded movie metadata.
scene.render.pixel_aspect_x = 32
scene.render.pixel_aspect_y = 27

print("[ntsc-preview] rendering 720x480 frames")
bpy.ops.render.render(animation=True)

ffmpeg_hits = glob.glob(os.path.join(ROOT, ".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*"))
ffmpeg = ffmpeg_hits[0] if ffmpeg_hits else shutil.which("ffmpeg") or "ffmpeg"
subprocess.run([
    ffmpeg, "-y", "-framerate", str(scene.render.fps), "-start_number", "1",
    "-i", os.path.join(FRAMES, "frame_%04d.png"),
    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    "-aspect", "16:9", MP4,
], check=True)
print("[ntsc-preview] wrote", MP4)
