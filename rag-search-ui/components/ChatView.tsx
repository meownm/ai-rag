
import React, { useState, useRef, useEffect } from 'react';
import { getAnswerStream } from '../services/api';
import { AnswerRequest, Message, SearchMode, ContextMode, StreamChunk } from '../types';
import ChatInput from './ChatInput';
import MessageItem from './MessageItem';
import SearchOptionsPanel from './SearchOptionsPanel';

interface ChatViewProps {
  conversationId: string | null;
}

const WelcomeScreen: React.FC = () => (
    <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
            <h1 className="text-4xl font-bold text-white">RAG Поиск</h1>
            <p className="mt-2 text-lg text-gray-400">Задавайте вопросы вашей базе знаний.</p>
        </div>
    </div>
);


const ChatView: React.FC<ChatViewProps> = ({ conversationId }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOptionsPanelOpen, setIsOptionsPanelOpen] = useState(false);
  const [searchOptions, setSearchOptions] = useState<Omit<AnswerRequest, 'query' | 'conversation_id' | 'stream'>>({
      mode: 'hybrid',
      context_mode: 'long',
      graph_depth: 2,
      top_k: 10,
      max_tokens: 2048,
      filters: {}
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSendMessage = (query: string) => {
    setError(null);
    setIsLoading(true);

    const userMessage: Message = { id: Date.now().toString(), role: 'user', content: query };
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      isLoading: true,
      citations: [],
    };
    setMessages(prev => [...prev, userMessage, assistantMessage]);

    const request: AnswerRequest = {
      ...searchOptions,
      query,
      conversation_id: conversationId,
      stream: true,
    };

    getAnswerStream(
      request,
      (chunk: StreamChunk) => {
        setMessages(prev =>
          prev.map(msg => {
            if (msg.id === assistantMessage.id) {
              if (chunk.type === 'text') {
                return { ...msg, content: msg.content + chunk.content };
              }
              if (chunk.type === 'metadata') {
                return { 
                  ...msg, 
                  isLoading: false, 
                  citations: chunk.citations,
                  graph_context: chunk.graph_context,
                  graph_status: chunk.graph_status,
                  enrichment_used: chunk.enrichment_used,
                  used_chunks: chunk.used_chunks,
                  used_tokens: chunk.used_tokens,
                  latency_ms: chunk.latency_ms,
                };
              }
            }
            return msg;
          })
        );
      },
      (err: Error) => {
        setError(`Ошибка: ${err.message}`);
        setMessages(prev => prev.slice(0, -1)); // Remove the loading assistant message
      },
      () => {
        setIsLoading(false);
        setMessages(prev => prev.map(msg => msg.id === assistantMessage.id ? {...msg, isLoading: false} : msg));
      }
    );
  };
  
  return (
    <div className="flex-1 flex flex-col relative overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
            {messages.length === 0 ? <WelcomeScreen /> : messages.map(msg => <MessageItem key={msg.id} message={msg} />) }
            {error && <div className="text-red-500 bg-red-900/20 p-3 rounded-md">{error}</div>}
            <div ref={messagesEndRef} />
        </div>
        <SearchOptionsPanel 
            isOpen={isOptionsPanelOpen}
            onClose={() => setIsOptionsPanelOpen(false)}
            options={searchOptions}
            setOptions={setSearchOptions}
        />
        <ChatInput 
            onSendMessage={handleSendMessage} 
            isLoading={isLoading} 
            toggleOptionsPanel={() => setIsOptionsPanelOpen(prev => !prev)}
        />
    </div>
  );
};

export default ChatView;