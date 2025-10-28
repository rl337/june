import { useState, useEffect, useRef } from 'react';
import io, { Socket } from 'socket.io-client';

interface UseWebSocketReturn {
  sendMessage: (message: any) => void;
  lastMessage: string | null;
  isConnected: boolean;
}

export const useWebSocket = (token: string, userId: string): UseWebSocketReturn => {
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    // Connect to WebSocket
    const socket = io(process.env.REACT_APP_WS_URL || 'ws://localhost:8000', {
      path: '/ws',
      query: { user_id: userId },
      transports: ['websocket']
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('Connected to WebSocket');
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('Disconnected from WebSocket');
      setIsConnected(false);
    });

    socket.on('message', (data: string) => {
      setLastMessage(data);
    });

    socket.on('error', (error: any) => {
      console.error('WebSocket error:', error);
    });

    return () => {
      socket.disconnect();
    };
  }, [userId]);

  const sendMessage = (message: any) => {
    if (socketRef.current && isConnected) {
      socketRef.current.emit('message', JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected');
    }
  };

  return {
    sendMessage,
    lastMessage,
    isConnected
  };
};
