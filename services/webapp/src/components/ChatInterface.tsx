import React, { useState, useEffect, useRef } from 'react';
import { Send, Mic, MicOff, Volume2, VolumeX, Bot, User, MoreVertical } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useAudioRecorder } from '../hooks/useAudioRecorder';
import { useAudioPlayer } from '../hooks/useAudioPlayer';
import MessageList from './MessageList';
import TypingIndicator from './TypingIndicator';

interface User {
  id: string;
  username: string;
  token: string;
}

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

interface ChatInterfaceProps {
  user: User;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ user }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const { sendMessage, lastMessage } = useWebSocket(user.token, user.id);
  const { isRecording, startRecording, stopRecording, audioBlob } = useAudioRecorder();
  const { playAudio, isPlaying, currentAudioUrl } = useAudioPlayer();

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle incoming WebSocket messages
  useEffect(() => {
    if (lastMessage) {
      const messageData = JSON.parse(lastMessage);
      
      if (messageData.type === 'response') {
        const newMessage: Message = {
          id: Date.now().toString(),
          type: 'text',
          content: messageData.text || 'No response received',
          sender: 'assistant',
          timestamp: new Date(),
          isGenerating: false
        };
        
        setMessages(prev => [...prev, newMessage]);
        setIsTyping(false);
      } else if (messageData.type === 'transcription') {
        // Update the last user message with transcription
        setMessages(prev => {
          const updated = [...prev];
          const lastUserMessage = updated.reverse().find(msg => msg.sender === 'user' && msg.isTranscribing);
          if (lastUserMessage) {
            lastUserMessage.content = messageData.text || 'Transcription failed';
            lastUserMessage.isTranscribing = false;
          }
          return updated.reverse();
        });
      } else if (messageData.type === 'audio_response') {
        const newMessage: Message = {
          id: Date.now().toString(),
          type: 'audio',
          content: 'Audio response',
          sender: 'assistant',
          timestamp: new Date(),
          audioUrl: messageData.audio_url
        };
        
        setMessages(prev => [...prev, newMessage]);
      } else if (messageData.type === 'error') {
        const newMessage: Message = {
          id: Date.now().toString(),
          type: 'system',
          content: `Error: ${messageData.message}`,
          sender: 'system',
          timestamp: new Date()
        };
        
        setMessages(prev => [...prev, newMessage]);
        setIsTyping(false);
      }
    }
  }, [lastMessage]);

  // Handle audio recording completion
  useEffect(() => {
    if (audioBlob) {
      const audioUrl = URL.createObjectURL(audioBlob);
      
      const newMessage: Message = {
        id: Date.now().toString(),
        type: 'audio',
        content: 'Voice message',
        sender: 'user',
        timestamp: new Date(),
        audioUrl: audioUrl,
        isTranscribing: true
      };
      
      setMessages(prev => [...prev, newMessage]);
      
      // Send audio to STT service
      sendMessage({
        type: 'audio',
        audio_data: 'base64_encoded_audio' // In real implementation, convert blob to base64
      });
    }
  }, [audioBlob, sendMessage]);

  const handleSendMessage = () => {
    if (!inputText.trim()) return;

    const newMessage: Message = {
      id: Date.now().toString(),
      type: 'text',
      content: inputText,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, newMessage]);
    setInputText('');
    setIsTyping(true);

    // Send message to gateway
    sendMessage({
      type: 'text',
      text: inputText
    });
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleTTSRequest = (text: string) => {
    sendMessage({
      type: 'tts_request',
      text: text
    });
  };

  const handlePlayAudio = (audioUrl: string) => {
    playAudio(audioUrl);
  };

  return (
    <div className="h-screen flex flex-col bg-telegram-light">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-telegram-blue rounded-full flex items-center justify-center">
            <Bot className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="font-semibold text-gray-900">June Agent</h1>
            <p className="text-sm text-gray-500">
              {isConnected ? 'Online' : 'Connecting...'}
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 bg-green-500 rounded-full"></div>
          <MoreVertical className="w-5 h-5 text-gray-400" />
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-hidden">
        <MessageList 
          messages={messages} 
          onPlayAudio={handlePlayAudio}
          onTTSRequest={handleTTSRequest}
          isPlaying={isPlaying}
          currentAudioUrl={currentAudioUrl}
        />
        {isTyping && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 p-4">
        <div className="flex items-end space-x-3">
          <div className="flex-1">
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type a message..."
              className="w-full px-4 py-3 border border-gray-300 rounded-2xl resize-none focus:ring-2 focus:ring-telegram-blue focus:border-transparent outline-none transition-all"
              rows={1}
              style={{ minHeight: '48px', maxHeight: '120px' }}
            />
          </div>
          
          <div className="flex items-center space-x-2">
            {/* Voice Recording Button */}
            <button
              onClick={isRecording ? stopRecording : startRecording}
              className={`w-12 h-12 rounded-full flex items-center justify-center transition-all ${
                isRecording 
                  ? 'bg-red-500 hover:bg-red-600 text-white' 
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
              }`}
            >
              {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </button>

            {/* Send Button */}
            <button
              onClick={handleSendMessage}
              disabled={!inputText.trim()}
              className="w-12 h-12 bg-telegram-blue rounded-full flex items-center justify-center text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
