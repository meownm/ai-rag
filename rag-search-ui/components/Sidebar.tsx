

import React, { useState, useEffect } from 'react';
import { ConversationInfo } from '../types';
import { getHistoryList, clearHistory } from '../services/api';

interface SidebarProps {
  onNewChat: () => void;
  onSelectConversation: (conversation: ConversationInfo) => void;
  activeSection: 'chat' | 'profile' | 'admin';
  onChangeSection: (section: 'chat' | 'profile' | 'admin') => void;
}

const Sidebar: React.FC<SidebarProps> = ({ onNewChat, onSelectConversation, activeSection, onChangeSection }) => {
  const [history, setHistory] = useState<ConversationInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
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

  const handleClearHistory = async () => {
    if (window.confirm('Вы уверены, что хотите очистить всю историю чатов? Это действие необратимо.')) {
      setIsClearing(true);
      setError(null);
      try {
        const userId = 'default-user';
        await clearHistory(userId);
        setHistory([]);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Произошла неизвестная ошибка';
        console.error("Failed to clear history:", err);
        alert(`Не удалось очистить историю: ${errorMessage}`);
        setError(`Не удалось очистить историю: ${errorMessage}`);
      } finally {
        setIsClearing(false);
      }
    }
  };

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
      <nav className="space-y-2 mb-4">
        {[
          { id: 'chat' as const, label: 'Чат' },
          { id: 'profile' as const, label: 'Мой профиль' },
          { id: 'admin' as const, label: 'Администрирование' },
        ].map(item => (
          <button
            key={item.id}
            onClick={() => onChangeSection(item.id)}
            className={`w-full text-left px-3 py-2 rounded-md transition-colors ${activeSection === item.id ? 'bg-gray-700 text-white' : 'text-gray-300 hover:bg-gray-700'}`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {activeSection === 'chat' && (
        <>
          <button
            onClick={onNewChat}
            className="w-full bg-teal-500 hover:bg-teal-600 text-white font-bold py-2 px-4 rounded transition-colors duration-200 mb-4"
          >
            + Новый чат
          </button>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">История</h2>
        </>
      )}
      <div className="flex-1 overflow-y-auto">
        {activeSection !== 'chat' ? (
          <div className="text-gray-500 text-sm">Выберите раздел, чтобы продолжить.</div>
        ) : isLoading ? (
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
      {activeSection === 'chat' && (
        <div className="mt-auto pt-4 border-t border-gray-700">
          <button
            onClick={handleClearHistory}
            disabled={isClearing}
            className="w-full bg-red-800 hover:bg-red-700 text-white font-bold py-2 px-4 rounded transition-colors duration-200 disabled:bg-gray-600 disabled:cursor-not-allowed flex items-center justify-center"
          >
            {isClearing ? (
               <>
                <div className="w-4 h-4 border-2 border-t-transparent border-white rounded-full animate-spin mr-2"></div>
                Очистка...
              </>
            ) : (
              'Очистить историю'
            )}
          </button>
        </div>
      )}
    </aside>
  );
};

export default Sidebar;
