import React, { useState, useEffect } from 'react';
import { ConversationInfo } from '../types';
import { getHistoryList } from '../services/api';

interface SidebarProps {
  onNewChat: () => void;
  onSelectConversation: (conversation: ConversationInfo) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ onNewChat, onSelectConversation }) => {
  const [history, setHistory] = useState<ConversationInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const userId = 'default-user'; // Replace with actual user management
        const data = await getHistoryList(userId);
        setHistory(data);
      } catch (error) {
        console.error("Failed to fetch history:", error);
        setError("Не удалось загрузить историю.");
      } finally {
        setIsLoading(false);
      }
    };
    fetchHistory();
  }, []);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <aside className="w-64 bg-gray-800 p-4 flex flex-col border-r border-gray-700">
      <button
        onClick={onNewChat}
        className="w-full bg-teal-500 hover:bg-teal-600 text-white font-bold py-2 px-4 rounded transition-colors duration-200 mb-4"
      >
        + Новый чат
      </button>
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">История</h2>
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="text-center text-gray-500">Загрузка...</div>
        ) : error ? (
          <div className="text-center text-red-500 p-2">{error}</div>
        ) : history.length > 0 ? (
          <nav className="space-y-1">
            {history.map(conv => (
              <a
                key={conv.conversation_id}
                href="#"
                onClick={(e) => { e.preventDefault(); onSelectConversation(conv); }}
                className="block p-2 rounded-md text-sm text-gray-300 hover:bg-gray-700 transition-colors"
              >
                <div className="flex flex-col">
                  <span className="font-medium truncate" title={conv.title || 'Чат без названия'}>
                    {conv.title || 'Чат без названия'}
                  </span>
                  <span className="text-xs text-gray-500 mt-1">
                    {formatDate(conv.created_at)}
                  </span>
                </div>
              </a>
            ))}
          </nav>
        ) : (
            <div className="text-center text-gray-500 text-sm p-4">
                История чатов пуста.
            </div>
        )}
      </div>
      <div className="mt-auto pt-4 border-t border-gray-700 text-xs text-gray-500">
        Очистка истории пока не поддерживается в API.
      </div>
    </aside>
  );
};

export default Sidebar;
