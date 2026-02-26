(() => {
  if (window.__secondBrainAudioMonitorInstalled) return;
  window.__secondBrainAudioMonitorInstalled = true;

  const SOURCE = "second_brain_page_audio_monitor";
  const trackedTracks = new Set();
  let micActive = false;

  function postMicActivity(active, reason) {
    window.postMessage(
      {
        source: SOURCE,
        kind: "mic_activity",
        active: !!active,
        reason: reason || "unknown"
      },
      "*"
    );
  }

  function recomputeMicActivity(reason) {
    const hasLiveTrack = Array.from(trackedTracks).some((track) => {
      if (!track) return false;
      return track.readyState === "live" && !track.muted && track.enabled;
    });

    if (hasLiveTrack === micActive) return;
    micActive = hasLiveTrack;
    postMicActivity(micActive, reason);
  }

  function watchAudioTrack(track) {
    if (!track || trackedTracks.has(track)) return;
    trackedTracks.add(track);

    const update = () => recomputeMicActivity("track_state_change");
    const cleanup = () => {
      trackedTracks.delete(track);
      recomputeMicActivity("track_ended");
    };

    track.addEventListener("mute", update);
    track.addEventListener("unmute", update);
    track.addEventListener("ended", cleanup, { once: true });

    recomputeMicActivity("new_track");
  }

  function handleAudioStream(stream) {
    if (!stream || typeof stream.getAudioTracks !== "function") return;
    const tracks = stream.getAudioTracks();
    if (!tracks || tracks.length === 0) return;
    for (const track of tracks) watchAudioTrack(track);
    recomputeMicActivity("stream_with_audio_tracks");
  }

  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices
    );

    navigator.mediaDevices.getUserMedia = async function patchedGetUserMedia(
      constraints
    ) {
      const stream = await originalGetUserMedia(constraints);
      const wantsAudio =
        constraints &&
        typeof constraints === "object" &&
        constraints.audio !== false;
      if (wantsAudio) {
        handleAudioStream(stream);
      }
      return stream;
    };
  }
})();
