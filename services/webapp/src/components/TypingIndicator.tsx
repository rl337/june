import React from 'react';
import { Bot } from 'lucide-react';

const TypingIndicator: React.FC = () => {
  return (
    <div className="flex justify-start px-4 py-2">
      <div className="flex items-center space-x-2">
        <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
          <Bot className="w-4 h-4 text-gray-600" />
        </div>
        <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3">
          <div className="flex items-center space-x-1">
            <span className="text-sm text-gray-500 mr-2">June is typing</span>
            <div className="flex space-x-1">
              <div className="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
              <div className="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
              <div className="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TypingIndicator;




