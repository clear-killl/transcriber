"""Create a tiny video with two audio tracks for an end-to-end MKV check."""
from pathlib import Path

import av
import numpy as np

root = Path(__file__).resolve().parents[1]
source, target = root / "data" / "russian-sample.wav", root / "data" / "two-tracks.mkv"
with av.open(str(source)) as input_container, av.open(str(target), "w", format="matroska") as output:
    rate = input_container.streams.audio[0].codec_context.sample_rate
    duration = input_container.duration / av.time_base
    video = output.add_stream("mpeg4", rate=1)
    video.width, video.height, video.pix_fmt = 64, 64, "yuv420p"
    tracks = []
    for language in ("eng", "rus"):
        track = output.add_stream("pcm_s16le", rate=rate)
        track.layout = "mono"
        track.metadata["language"] = language
        tracks.append(track)
    for number in range(int(duration) + 1):
        frame = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24")
        frame.pts = number
        for packet in video.encode(frame):
            output.mux(packet)
    for packet in video.encode(None):
        output.mux(packet)
    for decoded in input_container.decode(audio=0):
        for index, track in enumerate(tracks):
            samples = decoded.to_ndarray()
            if index == 0:
                samples = np.zeros_like(samples)
            frame = av.AudioFrame.from_ndarray(samples, format=decoded.format.name, layout="mono")
            frame.sample_rate, frame.pts = rate, decoded.pts
            for packet in track.encode(frame):
                output.mux(packet)
    for track in tracks:
        for packet in track.encode(None):
            output.mux(packet)
print(target)
