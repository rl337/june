import { useState, useRef, useCallback } from 'react';

interface UseAudioPlayerReturn {
  playAudio: (audioUrl: string) => void;
  isPlaying: boolean;
  currentAudioUrl?: string;
}

export const useAudioPlayer = (): UseAudioPlayerReturn => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentAudioUrl, setCurrentAudioUrl] = useState<string | undefined>();
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const playAudio = useCallback((audioUrl: string) => {
    // Stop current audio if playing
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }

    // Create new audio element
    const audio = new Audio(audioUrl);
    audioRef.current = audio;

    audio.onplay = () => {
      setIsPlaying(true);
      setCurrentAudioUrl(audioUrl);
    };

    audio.onpause = () => {
      setIsPlaying(false);
      setCurrentAudioUrl(undefined);
    };

    audio.onended = () => {
      setIsPlaying(false);
      setCurrentAudioUrl(undefined);
    };

    audio.onerror = (error) => {
      console.error('Audio playback error:', error);
      setIsPlaying(false);
      setCurrentAudioUrl(undefined);
    };

    audio.play().catch((error) => {
      console.error('Error playing audio:', error);
    });
  }, []);

  return {
    playAudio,
    isPlaying,
    currentAudioUrl
  };
};
