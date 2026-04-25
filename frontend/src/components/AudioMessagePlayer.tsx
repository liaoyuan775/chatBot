import { useEffect, useRef, useState } from "react";

type AudioMessagePlayerProps = {
  src: string;
  className?: string;
};

function formatDuration(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

export function AudioMessagePlayer({ src, className }: AudioMessagePlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [hoverRatio, setHoverRatio] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const rangeRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const syncTime = () => setCurrentTime(audio.currentTime || 0);
    const syncDuration = () => setDuration(audio.duration || 0);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => {
      setIsPlaying(false);
      setCurrentTime(0);
    };

    audio.addEventListener("timeupdate", syncTime);
    audio.addEventListener("loadedmetadata", syncDuration);
    audio.addEventListener("durationchange", syncDuration);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);

    return () => {
      audio.removeEventListener("timeupdate", syncTime);
      audio.removeEventListener("loadedmetadata", syncDuration);
      audio.removeEventListener("durationchange", syncDuration);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
    };
  }, []);

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      await audio.play().catch(() => undefined);
      return;
    }
    audio.pause();
  };

  const onSeek = (value: number) => {
    const audio = audioRef.current;
    if (!audio || !Number.isFinite(audio.duration)) return;
    audio.currentTime = value;
    setCurrentTime(value);
  };

  const progress = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;
  const previewRatio = hoverRatio ?? (duration > 0 ? currentTime / duration : 0);
  const previewTime = duration > 0 ? previewRatio * duration : 0;

  const updateHoverRatio = (clientX: number) => {
    const input = rangeRef.current;
    if (!input) return;
    const rect = input.getBoundingClientRect();
    if (!rect.width) return;
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    setHoverRatio(ratio);
  };

  return (
    <div className={`audio-message-player ${className ?? ""}`.trim()}>
      <audio ref={audioRef} src={src} preload="metadata" />
      <button
        type="button"
        className="audio-player-toggle"
        onClick={() => void togglePlayback()}
        aria-label={isPlaying ? "暂停音频" : "播放音频"}
      >
        {isPlaying ? "暂停" : "播放"}
      </button>
      <div className="audio-player-body">
        <div className="audio-player-meta">
          <span>{formatDuration(currentTime)}</span>
          <span className="audio-player-meta-sep">/</span>
          <span>{formatDuration(duration)}</span>
        </div>
        <div className="audio-player-track-shell">
          {(hoverRatio !== null || isDragging) && (
            <div className="audio-player-tooltip" style={{ left: `${previewRatio * 100}%` }}>
              {formatDuration(previewTime)}
            </div>
          )}
          <div className="audio-player-track">
            <div className="audio-player-progress" style={{ width: `${progress}%` }} />
            <div className="audio-player-buffer" />
            <div className="audio-player-thumb" style={{ left: `${progress}%` }} />
          </div>
        </div>
        <input
          ref={rangeRef}
          className="audio-player-range"
          type="range"
          min={0}
          max={duration || 0}
          step={0.01}
          value={Math.min(currentTime, duration || 0)}
          onChange={(event) => onSeek(Number(event.target.value))}
          onMouseMove={(event) => updateHoverRatio(event.clientX)}
          onMouseLeave={() => {
            if (!isDragging) setHoverRatio(null);
          }}
          onMouseDown={(event) => {
            setIsDragging(true);
            updateHoverRatio(event.clientX);
          }}
          onMouseUp={(event) => {
            updateHoverRatio(event.clientX);
            setIsDragging(false);
          }}
          onTouchStart={(event) => {
            setIsDragging(true);
            updateHoverRatio(event.touches[0].clientX);
          }}
          onTouchMove={(event) => updateHoverRatio(event.touches[0].clientX)}
          onTouchEnd={() => {
            setIsDragging(false);
            setHoverRatio(null);
          }}
          aria-label="音频进度"
        />
      </div>
    </div>
  );
}
