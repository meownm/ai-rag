
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '../types';
import CitationCard from './CitationCard';

const UserIcon = () => <div className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center font-bold text-white">П</div>;
const AssistantIcon = () => <div className="w-8 h-8 rounded-full bg-teal-600 flex items-center justify-center font-bold text-white">AI</div>;

const MessageItem: React.FC<{ message: Message }> = ({ message }) => {
  const isAssistant = message.role === 'assistant';

  return (
    <div className={`flex items-start gap-4 ${isAssistant ? '' : 'justify-end'}`}>
      {isAssistant && <AssistantIcon />}
      <div className={`max-w-2xl w-full ${isAssistant ? 'order-2' : 'order-1 text-right'}`}>
        <div className={`px-4 py-3 rounded-lg ${isAssistant ? 'bg-gray-800 text-left' : 'bg-gray-700'}`}>
            {message.isLoading && !message.content ? (
                <div className="flex items-center space-x-2">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse [animation-delay:-0.3s]"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse [animation-delay:-0.15s]"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse"></div>
                </div>
            ) : (
                <article className="prose prose-invert prose-p:text-gray-300 prose-headings:text-white prose-strong:text-white prose-a:text-teal-500">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {message.content}
                    </ReactMarkdown>
                </article>
            )}
        </div>
        
        {isAssistant && message.citations && message.citations.length > 0 && (
            <div className="mt-4 text-left">
                <h3 className="text-sm font-semibold text-gray-400 mb-2">Источники</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {message.citations.map(citation => (
                        <CitationCard key={citation.source_id} citation={citation} />
                    ))}
                </div>
            </div>
        )}
        {isAssistant && message.graph_context && message.graph_context.length > 0 && (
          <div className="mt-4 text-left">
            <h3 className="text-sm font-semibold text-gray-400 mb-2">Контекст графа ({message.graph_status})</h3>
            <pre className="bg-gray-800 p-3 rounded-md text-xs text-gray-400 overflow-x-auto">
              <code>{message.graph_context[0].content}</code>
            </pre>
          </div>
        )}
         {isAssistant && !message.isLoading && (message.used_tokens || message.latency_ms) && (
           <div className="mt-2 text-xs text-gray-500 text-left space-x-2">
             <span>Задержка: {message.latency_ms}мс</span>
             <span>|</span>
             <span>Токены: {message.used_tokens}</span>
             <span>|</span>
             <span>Чанки: {message.used_chunks}</span>
           </div>
         )}
      </div>
      {!isAssistant && <UserIcon />}
    </div>
  );
};

export default MessageItem;