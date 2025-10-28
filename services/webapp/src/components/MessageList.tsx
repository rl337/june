import React from 'react';
import { User, Bot, AlertCircle, Volume2, VolumeX } from 'lucide-react';
import MessageBubble from './MessageBubble';

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

interface MessageListProps {
  messages: Message[];
  onPlayAudio: (audioUrl: string) => void;
  onTTSRequest: (text: string) => void;
  isPlaying: boolean;
  currentAudioUrl?: string;
}

const MessageList: React.FC<MessageListProps> = ({ 
  messages, 
  onPlayAudio, 
  onTTSRequest, 
  isPlaying, 
  currentAudioUrl 
}) => {
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && (
        <div className="text-center py-12">
          <Bot className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-500 mb-2">Welcome to June Agent!</h3>
          <p className="text-gray-400">Start a conversation by typing a message or recording voice.</p>
        </div>
      )}
      
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div className={`flex items-start space-x-2 max-w-xs lg:max-w-md ${message.sender === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
            {/* Avatar */}
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
              message.sender === 'user' 
                ? 'bg-telegram-blue' 
                : message.sender === 'assistant'
                ? 'bg-gray-200'
                : 'bg-yellow-100'
            }`}>
              {message.sender === 'user' ? (
                <User className="w-4 h-4 text-white" />
              ) : message.sender === 'assistant' ? (
                <Bot className="w-4 h-4 text-gray-600" />
              ) : (
                <AlertCircle className="w-4 h-4 text-yellow-600" />
              )}
            </div>

            {/* Message Content */}
            <div className={`flex flex-col ${message.sender === 'user' ? 'items-end' : 'items-start'}`}>
              <MessageBubble
                message={message}
                onPlayAudio={onPlayAudio}
                onTTSRequest={onTTSRequest}
                isPlaying={isPlaying}
                currentAudioUrl={currentAudioUrl}
              />
              
              {/* Timestamp */}
              <span className="text-xs text-gray-400 mt-1 px-2">
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default MessageList;
