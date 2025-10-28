import React from 'react';
import { Volume2, VolumeX, Play, Pause, Loader2 } from 'lucide-react';

interface Message {
  id: string;
  type: 'text' | 'audio' | 'image' | 'system';
  content: string;
  sender: 'user' | 'assistant' | 'system';
  timestamp: Date;
  audioUrl?: string;
  isTranscribing?: boolean;
  isGenerating?: boolean;
}

interface MessageBubbleProps {
  message: Message;
  onPlayAudio: (audioUrl: string) => void;
  onTTSRequest: (text: string) => void;
  isPlaying: boolean;
  currentAudioUrl?: string;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ 
  message, 
  onPlayAudio, 
  onTTSRequest, 
  isPlaying, 
  currentAudioUrl 
}) => {
  const isCurrentAudio = currentAudioUrl === message.audioUrl;
  const isAudioPlaying = isPlaying && isCurrentAudio;

  const handlePlayAudio = () => {
    if (message.audioUrl) {
      onPlayAudio(message.audioUrl);
    }
  };

  const handleTTSRequest = () => {
    if (message.sender === 'assistant' && message.type === 'text') {
      onTTSRequest(message.content);
    }
  };

  if (message.type === 'system') {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-3 py-2 max-w-md">
        <p className="text-sm text-yellow-800">{message.content}</p>
      </div>
    );
  }

  if (message.type === 'audio') {
    return (
      <div className={`rounded-2xl px-4 py-3 max-w-xs ${
        message.sender === 'user' 
          ? 'bg-telegram-blue text-white' 
          : 'bg-gray-100 text-gray-800'
      }`}>
        <div className="flex items-center space-x-3">
          <button
            onClick={handlePlayAudio}
            disabled={!message.audioUrl}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
              message.sender === 'user'
                ? 'bg-white bg-opacity-20 hover:bg-opacity-30'
                : 'bg-telegram-blue hover:bg-blue-700'
            } ${!message.audioUrl ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {message.isTranscribing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : isAudioPlaying ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </button>
          
          <div className="flex-1">
            <p className="text-sm font-medium">
              {message.isTranscribing ? 'Transcribing...' : 'Voice message'}
            </p>
            {message.sender === 'assistant' && (
              <p className="text-xs opacity-75 mt-1">Click to play</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Text message
  return (
    <div className={`rounded-2xl px-4 py-3 max-w-xs lg:max-w-md ${
      message.sender === 'user' 
        ? 'bg-telegram-blue text-white' 
        : 'bg-white text-gray-800 border border-gray-200'
    }`}>
      <p className="text-sm whitespace-pre-wrap">{message.content}</p>
      
      {message.isGenerating && (
        <div className="flex items-center mt-2 space-x-1">
          <Loader2 className="w-3 h-3 animate-spin" />
          <span className="text-xs opacity-75">Generating...</span>
        </div>
      )}
      
      {/* TTS Button for assistant messages */}
      {message.sender === 'assistant' && message.type === 'text' && !message.isGenerating && (
        <button
          onClick={handleTTSRequest}
          className="mt-2 w-6 h-6 rounded-full bg-telegram-blue text-white hover:bg-blue-700 flex items-center justify-center transition-all"
          title="Convert to speech"
        >
          <Volume2 className="w-3 h-3" />
        </button>
      )}
    </div>
  );
};

export default MessageBubble;
