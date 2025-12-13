
import React, { useState, useRef, useEffect } from 'react';
import PaperAirplaneIcon from './icons/PaperAirplaneIcon';
import CogIcon from './icons/CogIcon';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  isLoading: boolean;
  toggleOptionsPanel: () => void;
}

const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, isLoading, toggleOptionsPanel }) => {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSendMessage = () => {
    if (message.trim() && !isLoading) {
      onSendMessage(message.trim());
      setMessage('');
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        const scrollHeight = textareaRef.current.scrollHeight;
        textareaRef.current.style.height = `${scrollHeight}px`;
    }
  }, [message]);

  return (
    <div className="px-4 pb-4 sm:px-6 sm:pb-6">
        <div className="relative flex items-end rounded-lg border border-gray-600 bg-gray-800 p-2">
            <button
                onClick={toggleOptionsPanel}
                className="p-2 text-gray-400 hover:text-white transition-colors duration-200"
                aria-label="Переключить опции поиска"
            >
                <CogIcon className="w-6 h-6" />
            </button>
            <textarea
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Задайте вопрос..."
                className="flex-1 bg-transparent border-none focus:ring-0 resize-none max-h-48 text-gray-300 placeholder-gray-500 px-2"
                rows={1}
                disabled={isLoading}
            />
            <button
                onClick={handleSendMessage}
                disabled={isLoading || !message.trim()}
                className="p-2 rounded-md text-white disabled:text-gray-500 disabled:cursor-not-allowed transition-colors duration-200"
                aria-label="Отправить сообщение"
            >
                {isLoading ? (
                    <div className="w-6 h-6 border-2 border-t-transparent border-white rounded-full animate-spin"></div>
                ) : (
                    <PaperAirplaneIcon className="w-6 h-6"/>
                )}
            </button>
        </div>
    </div>
  );
};

export default ChatInput;